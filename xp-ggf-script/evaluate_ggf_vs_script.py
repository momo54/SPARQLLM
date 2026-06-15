#!/usr/bin/env python3
"""Unified and fair GGF vs script evaluation harness."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Callable

BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parent
BENCH_DATA_DIR = BENCH_ROOT / "data"
BENCH_TMP_DIR = BENCH_ROOT / "tmp"
BENCH_OUT_DIR = BENCH_ROOT / "out"
LOCAL_REPO_ROOT = REPO_ROOT if (REPO_ROOT / "SPARQLLM").is_dir() else None

BENCH_TMP_DIR.mkdir(parents=True, exist_ok=True)
BENCH_OUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(BENCH_TMP_DIR / "mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(BENCH_TMP_DIR / "cache"))

import matplotlib.pyplot as plt
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

try:
    import SPARQLLM as _sparqllm  # noqa: F401
except ImportError:
    if LOCAL_REPO_ROOT is None:
        raise
    if str(LOCAL_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(LOCAL_REPO_ROOT))
    import SPARQLLM as _sparqllm  # noqa: F401

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.entity_graph_core import (
    METAQA_LABEL_PRED,
    compare_centered_graphs,
    extract_anchor_bracket,
    find_metaqa_anchor,
    graph_serialized_bytes,
    infer_metaqa_answer_relation,
    local_cbd_graph,
    metaqa_answer_terms_from_graph,
    metaqa_gold_answer_token_groups,
    metaqa_predicted_answer_tokens,
    random_sample_neighborhood,
    simrank_ranking,
    shortest_paths,
)
from SPARQLLM.metaqa_anchor_faiss import search_anchor_faiss
from SPARQLLM.metaqa_anchor_rerank import rerank_candidates_local
from SPARQLLM.udf.esbm import select_summary_triples
from SPARQLLM.udf.graph2text import graph_to_text
from SPARQLLM.udf.mcp.alias import _alias_llm
from SPARQLLM.udf.SPARQLLM import store as UDF_STORE
from SPARQLLM.entity_graph_core import expand_neighborhood_graph
from http_sparql import HttpMetrics, HttpSparqlClient, LocalGgfSparqlServer, LocalSparqlServer, sparql_iri_values


MQQA = "http://metaqa.org/qa#"
MENT = "http://metaqa.org/entity/"
MREL = "http://metaqa.org/relation/"
BENCH = Namespace("urn:xp-ggf-script:")
SCHEMA = Namespace("https://schema.org/")
VERBOSE = False


def default_config_path() -> str:
    local_config = REPO_ROOT / "config.ini"
    return str(local_config) if local_config.exists() else "config.ini"


def default_metaqa_kb_path() -> str:
    local_path = REPO_ROOT / "data" / "metaqa" / "MetaQA" / "kb.ttl"
    return str(local_path) if local_path.exists() else "data/metaqa/MetaQA/kb.ttl"


def default_metaqa_qa_path() -> str:
    local_path = REPO_ROOT / "data" / "metaqa" / "MetaQA" / "qa_2hop.ttl"
    return str(local_path) if local_path.exists() else "data/metaqa/MetaQA/qa_2hop.ttl"


def default_metaqa_graph_path() -> str:
    return default_metaqa_kb_path()


def default_metaqa_anchor_faiss_dir() -> str:
    local_path = REPO_ROOT / "xp-ggf-script" / "data" / "metaqa_anchor_faiss"
    return str(local_path) if local_path.exists() else "xp-ggf-script/data/metaqa_anchor_faiss"


def build_cli_env() -> dict[str, str]:
    env = os.environ.copy()
    if LOCAL_REPO_ROOT is not None:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{LOCAL_REPO_ROOT}{os.pathsep}{existing}" if existing else str(LOCAL_REPO_ROOT)
        )
    return env


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Unified GGF vs script evaluation harness")
    p.add_argument("--config", default=default_config_path())
    p.add_argument(
        "--cases",
        nargs="+",
        default=["expand", "paths", "simrank"],
        help="Cases to execute. Use 'all-local' or 'all'.",
    )
    p.add_argument("--graph", default=default_metaqa_graph_path())
    p.add_argument("--ggf-access", choices=["cli", "http"], default="cli")
    p.add_argument("--script-access", choices=["http", "local"], default="http")
    p.add_argument("--verbose", action="store_true", help="Print additional debug/progress details.")
    p.add_argument(
        "--http-latency-ms",
        type=float,
        default=0.0,
        help="Artificial latency added to each HTTP SPARQL call made by the benchmark client.",
    )
    p.add_argument("--ggf-http-timeout-s", type=float, default=300.0)
    p.add_argument("--format", default="turtle")
    p.add_argument("--entity", default="http://metaqa.org/entity/taxidermia")
    p.add_argument("--hops", type=int, default=1)
    p.add_argument("--direction", choices=["out", "in", "both"], default="both")
    p.add_argument(
        "--predicates",
        default="http://metaqa.org/relation/directed_by,http://metaqa.org/relation/written_by",
    )
    p.add_argument(
        "--nodes",
        default="http://metaqa.org/entity/avatar,http://metaqa.org/entity/titanic,http://metaqa.org/entity/aliens,http://metaqa.org/entity/the_abyss,http://metaqa.org/entity/james_cameron",
    )
    p.add_argument("--node-mode", choices=["touch", "induced"], default="induced")
    p.add_argument("--keep-literals", action="store_true", default=False)
    p.add_argument("--start", default="http://metaqa.org/entity/avatar")
    p.add_argument("--goal", default="http://metaqa.org/entity/titanic")
    p.add_argument("--max-depth", type=int, default=2)
    p.add_argument("--max-paths", type=int, default=10)
    p.add_argument("--center", default="http://metaqa.org/entity/taxidermia")
    p.add_argument("--decay", type=float, default=0.8)
    p.add_argument("--max-iter", type=int, default=5)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--max-nodes", type=int, default=500)
    p.add_argument("--ref-entity", default="http://metaqa.org/entity/avatar")
    p.add_argument("--lang", default="en")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    p.add_argument("--mode", choices=["degree", "random"], default="degree")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--sample-rate", type=float, default=0.5)
    p.add_argument("--schema-hops", type=int, default=2)
    p.add_argument("--schema-max-examples", type=int, default=2)
    p.add_argument("--candidate-limit", type=int, default=10)
    p.add_argument("--score-only-candidate-limit", type=int, default=20)
    p.add_argument("--score-only-candidate-year", type=int, default=2009)
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--out-json", default=str(BENCH_OUT_DIR / "ggf_vs_script_eval.json"))
    p.add_argument("--out-csv", default=str(BENCH_OUT_DIR / "ggf_vs_script_eval.csv"))
    p.add_argument("--out-plot", default=str(BENCH_OUT_DIR / "ggf_vs_script_eval.png"))
    p.add_argument("--metaqa-kb", default=default_metaqa_kb_path())
    p.add_argument("--metaqa-qa", default=default_metaqa_qa_path())
    p.add_argument("--metaqa-anchor-faiss-dir", default=default_metaqa_anchor_faiss_dir())
    p.add_argument("--anchor-search-top-k", type=int, default=20)
    p.add_argument("--anchor-output-top", type=int, default=5)
    p.add_argument(
        "--metaqa-limit",
        type=int,
        default=0,
        help="Maximum number of MetaQA questions to evaluate (0 = all questions in the QA TTL).",
    )
    p.add_argument("--metaqa-hops", type=int, default=2)
    p.add_argument("--metaqa-direction", choices=["out", "in", "both"], default="both")
    p.add_argument(
        "--metaqa-batch-size",
        type=int,
        default=100,
        help="Number of MetaQA questions per GGF batch query.",
    )
    p.add_argument(
        "--metaqa-anchor-batch-size",
        type=int,
        default=25,
        help="Number of MetaQA search/rerank questions per GGF batch query.",
    )
    return p.parse_args()


def normalize_cases(raw_cases: list[str]) -> list[str]:
    expanded: list[str] = []
    for case in raw_cases:
        if case == "all-local":
            expanded.extend(
                [
                    "expand",
                    "paths",
                    "simrank",
                    "random_sample",
                    "local_schema",
                    "metaqa_2hop_local",
                    "metaqa_anchor_search_rerank_local",
                ]
            )
        elif case == "all":
            expanded.extend(
                [
                    "expand",
                    "paths",
                    "simrank",
                    "random_sample",
                    "local_schema",
                    "metaqa_2hop_local",
                    "metaqa_anchor_search_rerank_local",
                    "cbd_esbm_summary",
                    "entity_similarity_compare",
                    "entity_similarity_score_only",
                ]
            )
        else:
            expanded.append(case)
    out: list[str] = []
    for case in expanded:
        if case not in out:
            out.append(case)
    return out


def canonical_json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def get_requests_config(args: argparse.Namespace) -> dict[str, str]:
    ConfigSingleton.reset_instance()
    cfg = ConfigSingleton(config_file=args.config).config
    return dict(cfg["Requests"])


def log_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def log_verbose(message: str) -> None:
    if VERBOSE:
        log_progress(f"[verbose] {message}")


def load_local_graph(path: str, fmt: str) -> Graph:
    g = Graph()
    g.parse(path, format=fmt)
    return g


def run_ggf_csv_query(
    config_path: str,
    query: str,
    load_path: str | None = None,
    load_format: str = "turtle",
) -> tuple[list[dict[str, str]], float]:
    BENCH_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ggf_eval_", dir=BENCH_TMP_DIR) as tmpdir:
        out_path = Path(tmpdir) / "result.csv"
        query_path = Path(tmpdir) / "query.sparql"
        metrics_path = Path(tmpdir) / "metrics.json"
        query_path.write_text(query, encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "SPARQLLM.cli.slm",
            "--config",
            config_path,
            "-f",
            str(query_path),
            "-o",
            str(out_path),
            "--metrics-out",
            str(metrics_path),
        ]
        if load_path is not None:
            cmd.extend(["--load", load_path, "--format", load_format])
        log_verbose(
            "running GGF query via CLI "
            f"(load_path={load_path or '<none>'}, format={load_format}, query_bytes={len(query.encode('utf-8'))})"
        )
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, env=build_cli_env())
        elapsed = time.perf_counter() - started
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        if metrics_path.exists():
            metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            elapsed = float(metrics_payload.get("execution_wall_time_s", elapsed))
        with out_path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        log_verbose(f"GGF query completed in {elapsed:.3f}s with {len(rows)} CSV row(s)")
    return rows, elapsed


def _http_rows_to_str_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def get_ggf_http_client(args: argparse.Namespace) -> HttpSparqlClient:
    client = getattr(args, "_ggf_http_client", None)
    if client is None:
        raise RuntimeError("GGF HTTP SPARQL client is not initialized.")
    return client


def _resolved_path(path: str | None) -> str:
    if not path:
        return ""
    return str(Path(path).expanduser().resolve())


def run_ggf_query(
    args: argparse.Namespace,
    query: str,
    load_path: str | None = None,
    load_format: str = "turtle",
) -> tuple[list[dict[str, str]], float, HttpMetrics | None]:
    if args.ggf_access == "cli":
        rows, elapsed = run_ggf_csv_query(args.config, query, load_path=load_path, load_format=load_format)
        return rows, elapsed, None

    expected_load_path = getattr(args, "_ggf_http_load_path", "")
    requested_load_path = _resolved_path(load_path)
    if requested_load_path and expected_load_path and requested_load_path != expected_load_path:
        raise RuntimeError(
            "GGF HTTP server was started with a different loaded graph "
            f"({expected_load_path}) than this case requested ({requested_load_path})."
        )

    client = get_ggf_http_client(args)
    client.metrics = HttpMetrics()
    started = time.perf_counter()
    rows = client.select(query, timeout=float(args.ggf_http_timeout_s))
    elapsed = time.perf_counter() - started
    metrics = HttpMetrics(
        call_count=client.metrics.call_count,
        upload_bytes=client.metrics.upload_bytes,
        download_bytes=client.metrics.download_bytes,
    )
    log_verbose(
        "GGF query completed via HTTP "
        f"in {elapsed:.3f}s with {len(rows)} row(s), transfer={metrics.upload_bytes + metrics.download_bytes}B"
    )
    return _http_rows_to_str_rows(rows), elapsed, metrics


def get_http_client(args: argparse.Namespace) -> HttpSparqlClient:
    client = getattr(args, "_http_client", None)
    if client is None:
        raise RuntimeError("HTTP SPARQL client is not initialized.")
    return client


def reset_http_metrics(args: argparse.Namespace) -> HttpSparqlClient:
    client = get_http_client(args)
    client.metrics = HttpMetrics()
    log_verbose("reset HTTP metrics for script-side client")
    return client


def script_http_metrics(client: HttpSparqlClient, normalized_output: Any, wall_time_s: float, _note: str) -> dict[str, Any]:
    output_bytes = canonical_json_bytes(normalized_output)
    return {
        "wall_time_s": round(wall_time_s, 6),
        "logical_call_count": client.metrics.call_count,
        "upload_bytes": client.metrics.upload_bytes,
        "download_bytes": client.metrics.download_bytes,
        "output_bytes": output_bytes,
        "transfer_total_bytes": client.metrics.upload_bytes + client.metrics.download_bytes,
        "transfer_definition": "SPARQL HTTP request/response bytes only",
    }


def ggf_http_result_metrics(http_metrics: HttpMetrics, normalized_output: Any, wall_time_s: float, _note: str) -> dict[str, Any]:
    output_bytes = canonical_json_bytes(normalized_output)
    return {
        "wall_time_s": round(wall_time_s, 6),
        "logical_call_count": http_metrics.call_count,
        "upload_bytes": http_metrics.upload_bytes,
        "download_bytes": http_metrics.download_bytes,
        "output_bytes": output_bytes,
        "transfer_total_bytes": http_metrics.upload_bytes + http_metrics.download_bytes,
        "transfer_definition": "SPARQL HTTP request/response bytes only",
    }


def add_http_metrics(total: HttpMetrics, metrics: HttpMetrics) -> None:
    total.call_count += metrics.call_count
    total.upload_bytes += metrics.upload_bytes
    total.download_bytes += metrics.download_bytes


def _sparql_rows_to_triples(rows: list[dict[str, Any]]) -> list[list[str]]:
    out: list[list[str]] = []
    for row in rows:
        s = row.get("s")
        p = row.get("p")
        o = row.get("o")
        if s is None or p is None or o is None:
            continue
        out.append([str(s), str(p), str(o)])
    out.sort()
    return out


def http_fetch_all_graph(client: HttpSparqlClient) -> Graph:
    rows = client.select(
        "SELECT ?s ?p ?o WHERE { ?s ?p ?o . FILTER(isIRI(?s)) } ORDER BY ?s ?p ?o"
    )
    return client.rows_to_graph(rows)


def http_build_simrank_graph_naive(client: HttpSparqlClient, center: str, max_nodes: int) -> Graph:
    center_ref = URIRef(center)
    seen: set[str] = {center}
    queue: deque[str] = deque([center])
    discovered: list[str] = []
    edge_pred = BENCH["simrankEdge"]
    graph = Graph()

    while queue:
        node = queue.popleft()
        discovered.append(node)

        for predicate in http_fetch_node_predicates(client, node, "out"):
            step_graph = http_fetch_node_predicate_graph(client, node, predicate, "out")
            for s, _, o in step_graph:
                if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                    continue
                graph.add((s, edge_pred, o))
                target = str(o)
                if target not in seen and len(seen) < max_nodes:
                    seen.add(target)
                    queue.append(target)

        for predicate in http_fetch_node_predicates(client, node, "in"):
            step_graph = http_fetch_node_predicate_graph(client, node, predicate, "in")
            for s, _, o in step_graph:
                if not isinstance(s, URIRef) or not isinstance(o, URIRef):
                    continue
                graph.add((s, edge_pred, o))
                source = str(s)
                if source not in seen and len(seen) < max_nodes:
                    seen.add(source)
                    queue.append(source)

        if len(discovered) >= max_nodes:
            break

    if center not in seen:
        return Graph()
    return graph


def http_fetch_step_graph(client: HttpSparqlClient, nodes: list[str], direction: str) -> Graph:
    if not nodes:
        return Graph()
    query = (
        f"SELECT DISTINCT ?s ?p ?o WHERE {{ {sparql_iri_values('s', nodes)} ?s ?p ?o . }}"
        if direction == "out"
        else f"SELECT DISTINCT ?s ?p ?o WHERE {{ {sparql_iri_values('o', nodes)} ?s ?p ?o . }}"
    )
    rows = client.select(query)
    return client.rows_to_graph(rows)


def http_expand_neighborhood_graph(client: HttpSparqlClient, seeds: list[str], hops: int, direction: str = "both") -> Graph:
    out = Graph()
    if hops < 0:
        return out
    mode = direction.lower().strip() or "both"
    if mode not in {"out", "in", "both"}:
        mode = "both"
    frontier = [seed for seed in seeds if seed]
    seen_depth: dict[str, int] = {seed: 0 for seed in frontier}
    depth = 0
    while frontier and depth < hops:
        next_nodes: set[str] = set()
        if mode in {"out", "both"}:
            step_graph = http_fetch_step_graph(client, frontier, "out")
            for s, p, o in step_graph:
                out.add((s, p, o))
                if isinstance(o, URIRef):
                    next_depth = depth + 1
                    prev = seen_depth.get(str(o))
                    if prev is None or next_depth < prev:
                        seen_depth[str(o)] = next_depth
                        next_nodes.add(str(o))
        if mode in {"in", "both"}:
            step_graph = http_fetch_step_graph(client, frontier, "in")
            for s, p, o in step_graph:
                out.add((s, p, o))
                if isinstance(s, URIRef):
                    next_depth = depth + 1
                    prev = seen_depth.get(str(s))
                    if prev is None or next_depth < prev:
                        seen_depth[str(s)] = next_depth
                        next_nodes.add(str(s))
        frontier = sorted(next_nodes)
        depth += 1
    return out


def http_fetch_cbd_graph(client: HttpSparqlClient, entity: str) -> Graph:
    query = f"""SELECT ?s ?p ?o WHERE {{
  BIND(<{entity}> AS ?s)
  ?s ?p ?o .
}} ORDER BY ?p ?o"""
    rows = client.select(query)
    return client.rows_to_graph(rows)


def http_fetch_labels_graph(client: HttpSparqlClient, entities: list[str]) -> Graph:
    graph = Graph()
    values = [entity for entity in entities if entity]
    if not values:
        return graph
    query = f"""SELECT ?s ?p ?o WHERE {{
  {sparql_iri_values('s', values)}
  OPTIONAL {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> ?rdfsLabel . }}
  OPTIONAL {{ ?s <{METAQA_LABEL_PRED}> ?metaqaLabel . }}
  BIND(COALESCE(?rdfsLabel, ?metaqaLabel) AS ?o)
  BIND(<http://www.w3.org/2000/01/rdf-schema#label> AS ?p)
  FILTER(BOUND(?o))
}}"""
    rows = client.select(query)
    for row in rows:
        s = row.get("s")
        p = row.get("p")
        o = row.get("o")
        if s is None or p is None or o is None:
            continue
        graph.add((s, p, o))
    return graph


def http_fetch_node_predicates(client: HttpSparqlClient, node: str, direction: str) -> list[str]:
    if direction == "out":
        query = f"SELECT DISTINCT ?p WHERE {{ <{node}> ?p ?o . }} ORDER BY ?p"
    else:
        query = f"SELECT DISTINCT ?p WHERE {{ ?s ?p <{node}> . }} ORDER BY ?p"
    rows = client.select(query)
    return [str(row["p"]) for row in rows if row.get("p") is not None]


def http_fetch_node_predicate_graph(client: HttpSparqlClient, node: str, predicate: str, direction: str) -> Graph:
    if direction == "out":
        query = f"SELECT ?s ?p ?o WHERE {{ BIND(<{node}> AS ?s) ?s <{predicate}> ?o . BIND(<{predicate}> AS ?p) }} ORDER BY ?o"
    else:
        query = f"SELECT ?s ?p ?o WHERE {{ ?s <{predicate}> ?o . FILTER(?o = <{node}>) BIND(<{predicate}> AS ?p) }} ORDER BY ?s"
    rows = client.select(query)
    return client.rows_to_graph(rows)


def http_expand_neighborhood_graph_naive(client: HttpSparqlClient, seeds: list[str], hops: int, direction: str = "both") -> Graph:
    out = Graph()
    if hops < 0:
        return out
    mode = direction.lower().strip() or "both"
    if mode not in {"out", "in", "both"}:
        mode = "both"
    frontier = [seed for seed in seeds if seed]
    seen_depth: dict[str, int] = {seed: 0 for seed in frontier}
    depth = 0
    while frontier and depth < hops:
        next_nodes: set[str] = set()
        for node in frontier:
            if mode in {"out", "both"}:
                for predicate in http_fetch_node_predicates(client, node, "out"):
                    step_graph = http_fetch_node_predicate_graph(client, node, predicate, "out")
                    for s, p, o in step_graph:
                        out.add((s, p, o))
                        if isinstance(o, URIRef):
                            next_depth = depth + 1
                            prev = seen_depth.get(str(o))
                            if prev is None or next_depth < prev:
                                seen_depth[str(o)] = next_depth
                                next_nodes.add(str(o))
            if mode in {"in", "both"}:
                for predicate in http_fetch_node_predicates(client, node, "in"):
                    step_graph = http_fetch_node_predicate_graph(client, node, predicate, "in")
                    for s, p, o in step_graph:
                        out.add((s, p, o))
                        if isinstance(s, URIRef):
                            next_depth = depth + 1
                            prev = seen_depth.get(str(s))
                            if prev is None or next_depth < prev:
                                seen_depth[str(s)] = next_depth
                                next_nodes.add(str(s))
        frontier = sorted(next_nodes)
        depth += 1
    return out


def sparql_iri_in_expr(var_name: str, iris: set[str]) -> str:
    if not iris:
        return "false"
    joined = ", ".join(f"<{iri}>" for iri in sorted(iris))
    return f"?{var_name} IN ({joined})"


def triples_from_csv_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    return sorted([[row["s"], row["p"], row["o"]] for row in rows])


def summary_rows_from_csv_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = [
        {
            "entity": row["entity"],
            "entityLabel": row["entityLabel"],
            "s": row["s"],
            "p": row["p"],
            "o": row["o"],
        }
        for row in rows
    ]
    normalized.sort(key=lambda row: (row["entityLabel"], row["s"], row["p"], row["o"]))
    return normalized


def typing_rows_from_csv_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = [
        {
            "entity": row["entity"],
            "entityLabel": row["entityLabel"],
            "predictedType": row.get("predictedType", ""),
            "justification": row.get("justification", ""),
        }
        for row in rows
    ]
    normalized.sort(key=lambda row: (row["entityLabel"], row["predictedType"], row["justification"]))
    return normalized


def ranking_from_csv_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {"rank": int(row["rank"]), "entity": row["entity"], "score": float(row["score"])}
        for row in rows
    ]


def random_sample_from_csv_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    predicate_stats: list[dict[str, Any]] = []

    seen_stats: set[tuple[int, str]] = set()
    for row in rows:
        row_type = row.get("rowType", "")
        if row_type == "meta" and not metadata:
            metadata = {
                "sampleRate": float(row["sampleRate"]),
                "exactTripleCount": int(row["exactTripleCount"]),
                "sampledTripleCount": int(row["sampledTripleCount"]),
                "estimatedTripleCount": float(row["estimatedTripleCount"]),
                "absoluteError": float(row["absoluteError"]),
                "relativeError": float(row["relativeError"]),
            }
        elif row_type == "stat":
            key = (int(row["rank"]), row["property"])
            if key in seen_stats:
                continue
            seen_stats.add(key)
            predicate_stats.append(
                {
                    "rank": key[0],
                    "property": key[1],
                    "exactFrequency": int(row["exactFrequency"]),
                    "sampledFrequency": int(row["sampledFrequency"]),
                    "estimatedFrequency": float(row["estimatedFrequency"]),
                    "absoluteError": float(row["predicateAbsoluteError"]),
                    "relativeError": float(row["predicateRelativeError"]),
                }
            )

    predicate_stats.sort(key=lambda row: (row["rank"], row["property"]))
    return {
        "metadata": metadata,
        "predicateStats": predicate_stats,
    }


def canonicalize_paths_csv_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    grouped: dict[int, list[tuple[int, str, str, str]]] = {}
    for row in rows:
        path_rank = int(row["pathRank"])
        grouped.setdefault(path_rank, []).append((int(row["stepPos"]), row["src"], row["pred"], row["dst"]))

    paths: list[list[dict[str, str]]] = []
    for _, steps in grouped.items():
        ordered_steps = sorted(steps, key=lambda x: x[0])
        paths.append([{"src": s, "pred": p, "dst": o} for _, s, p, o in ordered_steps])
    paths.sort(key=lambda path: tuple((step["src"], step["pred"], step["dst"]) for step in path))
    return paths


def bool_literal(flag: bool) -> str:
    return "true" if flag else "false"


def build_expand_query(args: argparse.Namespace) -> str:
    return f'''PREFIX ggf: <http://ggf.org/>\nSELECT ?s ?p ?o WHERE {{\n  BIND(ggf:EXPAND(<{args.entity}>, {args.hops}, "{args.direction}") AS ?gOut)\n  GRAPH ?gOut {{ ?s ?p ?o . }}\n}}\nORDER BY ?s ?p ?o\n'''


def build_paths_query(args: argparse.Namespace) -> str:
    return f'''PREFIX ggf: <http://ggf.org/>\nPREFIX slm: <http://sparqllm/slm#>\nSELECT ?pathRank ?stepPos ?src ?pred ?dst WHERE {{\n  BIND(ggf:PATHS(<{args.start}>, <{args.goal}>, {args.max_depth}, "{args.direction}", {args.max_paths}) AS ?gOut)\n  GRAPH ?gOut {{\n    ?root a slm:PathSet ; slm:hasPath ?path .\n    ?path a slm:Path ; slm:rank ?pathRank ; slm:hasStep ?step .\n    ?step a slm:PathStep ; slm:pos ?stepPos ; slm:src ?src ; slm:pred ?pred ; slm:dst ?dst .\n  }}\n}}\nORDER BY ?pathRank ?stepPos\n'''


def build_simrank_query(args: argparse.Namespace) -> str:
    return f'''PREFIX ggf: <http://ggf.org/>\nPREFIX cand: <http://example.org/cand#>\nSELECT ?rank ?entity ?score WHERE {{\n  BIND(ggf:SIMRANK(<{args.center}>, {args.decay}, {args.max_iter}, {args.top_k}, {args.max_nodes}) AS ?gOut)\n  GRAPH ?gOut {{\n    ?root a cand:SimRankResult ; cand:center <{args.center}> ; cand:candidate ?node .\n    ?node a cand:SimRankNode ; cand:entity ?entity ; cand:score ?score ; cand:rank ?rank .\n  }}\n}}\nORDER BY ?rank\n'''


def build_random_sample_query(args: argparse.Namespace) -> str:
    return f'''PREFIX cand: <http://example.org/cand#>\nPREFIX ggf: <http://ggf.org/>\nSELECT ?rowType ?sampleRate ?exactTripleCount ?sampledTripleCount ?estimatedTripleCount ?absoluteError ?relativeError ?rank ?property ?exactFrequency ?sampledFrequency ?estimatedFrequency ?predicateAbsoluteError ?predicateRelativeError WHERE {{\n  BIND(ggf:RANDOM-SAMPLE(<{args.entity}>, {args.hops}, "{args.direction}", {args.sample_rate}, {args.seed}) AS ?gSample)\n  GRAPH ?gSample {{\n    {{\n      ?root a cand:RandomSample ;\n            cand:sampleRate ?sampleRate ;\n            cand:exactTripleCount ?exactTripleCount ;\n            cand:sampledTripleCount ?sampledTripleCount ;\n            cand:estimatedTripleCount ?estimatedTripleCount ;\n            cand:absoluteError ?absoluteError ;\n            cand:relativeError ?relativeError .\n      BIND("meta" AS ?rowType)\n    }}\n    UNION\n    {{\n      ?root a cand:RandomSample ;\n            cand:predicateStat ?stat .\n      ?stat a cand:PredicateEstimate ;\n            cand:rank ?rank ;\n            cand:property ?property ;\n            cand:exactFrequency ?exactFrequency ;\n            cand:sampledFrequency ?sampledFrequency ;\n            cand:estimatedFrequency ?estimatedFrequency ;\n            cand:absoluteError ?predicateAbsoluteError ;\n            cand:relativeError ?predicateRelativeError .\n      BIND("stat" AS ?rowType)\n    }}\n  }}\n}}\nORDER BY ?rowType ?rank ?property\n'''


def build_cbd_esbm_query(args: argparse.Namespace) -> str:
    return f'''PREFIX mrel: <http://metaqa.org/relation/>\nPREFIX ggf: <http://ggf.org/>\nSELECT ?entity ?entityLabel ?s ?p ?o WHERE {{\n  {{\n    SELECT ?entity ?entityLabel WHERE {{\n      ?entity mrel:release_year ?year .\n      FILTER(?entity != <{args.ref_entity}>)\n      BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n    }} ORDER BY ?entityLabel LIMIT {args.candidate_limit}\n  }}\n  BIND(ggf:CBD(?entity) AS ?gCBD)\n  BIND(ggf:SUMMARY(?gCBD, ?entity, {args.k}, "{args.neighborhood}", "{args.mode}", {args.seed}) AS ?gSummary)\n  GRAPH ?gSummary {{ ?s ?p ?o . }}\n}}\nORDER BY ?entityLabel ?s ?p ?o\n'''


def build_local_schema_query(args: argparse.Namespace) -> str:
    return f'''PREFIX cand: <http://example.org/cand#>\nPREFIX ggf: <http://ggf.org/>\nSELECT ?rank ?hopCount ?direction ?property ?frequency ?exampleNeighbor ?exampleNeighborLabel ?exampleLiteral WHERE {{\n  BIND(ggf:LOCAL-SCHEMA(<{args.entity}>, {args.schema_hops}, "{args.direction}", {args.schema_max_examples}) AS ?gSchema)\n  GRAPH ?gSchema {{\n    ?root a cand:LocalSchema ;\n          cand:slot ?slot .\n    ?slot a cand:SchemaSlot ;\n          cand:rank ?rank ;\n          cand:hopCount ?hopCount ;\n          cand:direction ?direction ;\n          cand:property ?property ;\n          cand:frequency ?frequency .\n    OPTIONAL {{\n      ?slot cand:exampleNeighbor ?exampleNeighbor .\n      OPTIONAL {{ ?exampleNeighbor <http://www.w3.org/2000/01/rdf-schema#label> ?exampleNeighborLabel . }}\n    }}\n    OPTIONAL {{ ?slot cand:exampleLiteral ?exampleLiteral . }}\n  }}\n}}\nORDER BY ?rank ?exampleNeighbor ?exampleLiteral\n'''


def build_entity_similarity_query(args: argparse.Namespace) -> str:
    return f'''PREFIX mrel: <http://metaqa.org/relation/>\nPREFIX cand: <http://example.org/cand#>\nPREFIX ggf: <http://ggf.org/>\nSELECT ?entity ?entityLabel ?score ?shared ?differing ?exclusive WHERE {{\n  VALUES ?refEntity {{ <{args.ref_entity}> }}\n  {{\n    SELECT ?entity ?entityLabel WHERE {{\n      ?entity mrel:release_year ?year .\n      FILTER(?entity != <{args.ref_entity}>)\n      BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n    }} ORDER BY ?entityLabel LIMIT {args.candidate_limit}\n  }}\n  BIND(ggf:CBD(?refEntity) AS ?gRefCBD)\n  BIND(ggf:SUMMARY(?gRefCBD, ?refEntity, {args.k}, "{args.neighborhood}", "{args.mode}", {args.seed}) AS ?gRefSummary)\n  BIND(ggf:CBD(?entity) AS ?gEntCBD)\n  BIND(ggf:SUMMARY(?gEntCBD, ?entity, {args.k}, "{args.neighborhood}", "{args.mode}", {args.seed}) AS ?gEntSummary)\n  BIND(ggf:COMPARE-GRAPHS(?gRefSummary, ?gEntSummary, ?refEntity, ?entity) AS ?gCmp)\n  GRAPH ?gCmp {{\n    ?root a cand:Comparison ;\n          cand:sharedCount ?shared ;\n          cand:differingCount ?differing ;\n          cand:exclusiveCount ?exclusive ;\n          cand:similarityScore ?score .\n  }}\n}}\nORDER BY DESC(?score) DESC(?shared) ?entityLabel\nLIMIT {args.top}\n'''


def build_entity_similarity_score_only_query(args: argparse.Namespace) -> str:
    return f'''PREFIX mrel: <http://metaqa.org/relation/>\nPREFIX cand: <http://example.org/cand#>\nPREFIX ggf: <http://ggf.org/>\nSELECT ?entity ?score WHERE {{\n  VALUES ?refEntity {{ <{args.ref_entity}> }}\n  {{\n    SELECT ?entity WHERE {{\n      ?entity mrel:release_year {args.score_only_candidate_year} .\n      FILTER(?entity != <{args.ref_entity}>)\n    }} ORDER BY ?entity LIMIT {args.score_only_candidate_limit}\n  }}\n  BIND(ggf:CBD(?refEntity) AS ?gRefCBD)\n  BIND(ggf:SUMMARY(?gRefCBD, ?refEntity, {args.k}, "{args.neighborhood}", "{args.mode}", {args.seed}) AS ?gRefSummary)\n  BIND(ggf:CBD(?entity) AS ?gEntCBD)\n  BIND(ggf:SUMMARY(?gEntCBD, ?entity, {args.k}, "{args.neighborhood}", "{args.mode}", {args.seed}) AS ?gEntSummary)\n  BIND(ggf:COMPARE-GRAPHS(?gRefSummary, ?gEntSummary, ?refEntity, ?entity) AS ?gCmp)\n  GRAPH ?gCmp {{\n    ?root cand:similarityScore ?score .\n  }}\n}}\nORDER BY DESC(?score) ?entity\nLIMIT {args.top}\n'''


def build_entity_typing_query(args: argparse.Namespace) -> str:
    return f'''PREFIX mrel: <http://metaqa.org/relation/>\nPREFIX ggf: <http://ggf.org/>\nPREFIX schema: <https://schema.org/>\nSELECT ?entity ?entityLabel ?predictedType ?justification WHERE {{\n  VALUES ?refEntity {{ <{args.ref_entity}> }}\n  {{\n    SELECT ?entity ?entityLabel WHERE {{\n      ?entity mrel:release_year ?year .\n      FILTER(?entity != <{args.ref_entity}>)\n      BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n    }} ORDER BY ?entityLabel LIMIT {args.candidate_limit}\n  }}\n  BIND(ggf:CBD(?entity) AS ?gCBD)\n  BIND(ggf:GRAPH2TEXT(?gCBD) AS ?gText)\n  GRAPH ?gText {{\n    ?textRoot schema:text ?contextText .\n  }}\n  BIND(\n    CONCAT(\n      "Infer the most likely semantic type(s) of this entity from its local graph context.\\n",\n      "Return ONLY a JSON-LD object in this exact shape:\\n",\n      "{{\\n",\n      "  \\"@context\\": \\"https://schema.org/\\",\\n",\n      "  \\"@type\\": \\"Thing\\",\\n",\n      "  \\"name\\": \\"entity label\\",\\n",\n      "  \\"additionalType\\": [\\"type1\\", \\"type2\\"],\\n",\n      "  \\"description\\": \\"short justification\\"\\n",\n      "}}\\n\\n",\n      "Entity: ", ?entityLabel, "\\n",\n      "Local graph context:\\n", ?contextText, "\\n"\n    )\n    AS ?prompt\n  )\n  BIND(ggf:LLM(?prompt) AS ?gLLM)\n  GRAPH ?gLLM {{\n    ?root a schema:Thing .\n    OPTIONAL {{ ?root schema:additionalType ?predictedType . }}\n    OPTIONAL {{ ?root schema:description ?justification . }}\n  }}\n}}\nORDER BY ?entityLabel ?predictedType\n'''


def metaqa_candidate_pool(
    source: Graph,
    ref_entity: str,
    limit_n: int,
    release_year_filter: int | None = None,
) -> list[dict[str, str]]:
    release_year_pred = URIRef(f"{MREL}release_year")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for subject, _, year_value in source.triples((None, release_year_pred, None)):
        if release_year_filter is not None and str(year_value) != str(release_year_filter):
            continue
        entity = str(subject)
        if entity == ref_entity or entity in seen:
            continue
        seen.add(entity)
        rows.append(
            {
                "entity": entity,
                "entityLabel": entity.rsplit("/", 1)[-1],
            }
        )
    rows.sort(key=lambda row: row["entityLabel"])
    return rows[:limit_n]


def build_entity_typing_prompt(entity_label: str, context_text: str) -> str:
    return (
        "Infer the most likely semantic type(s) of this entity from its local graph context.\n"
        "Return ONLY a JSON-LD object in this exact shape:\n"
        "{\n"
        '  "@context": "https://schema.org/",\n'
        '  "@type": "Thing",\n'
        '  "name": "entity label",\n'
        '  "additionalType": ["type1", "type2"],\n'
        '  "description": "short justification"\n'
        "}\n\n"
        f"Entity: {entity_label}\n"
        f"Local graph context:\n{context_text}\n"
    )


def typing_rows_from_graph(entity: str, entity_label: str, graph: Graph) -> list[dict[str, str]]:
    roots = sorted({root for root in graph.subjects(RDF.type, SCHEMA.Thing)}, key=str)
    rows: list[dict[str, str]] = []
    for root in roots:
        predicted_types = [str(obj) for obj in graph.objects(root, SCHEMA.additionalType)]
        justifications = [str(obj) for obj in graph.objects(root, SCHEMA.description)]
        if not predicted_types:
            predicted_types = [""]
        if not justifications:
            justifications = [""]
        for predicted_type in predicted_types:
            for justification in justifications:
                rows.append(
                    {
                        "entity": entity,
                        "entityLabel": entity_label,
                        "predictedType": predicted_type,
                        "justification": justification,
                    }
                )
    rows.sort(key=lambda row: (row["entityLabel"], row["predictedType"], row["justification"]))
    return rows


def label_for(source: Graph, node: URIRef, label_source: Graph | None = None) -> str:
    labels = source if label_source is None else label_source
    rdfs_labels = sorted({str(obj) for obj in labels.objects(node, RDFS.label) if str(obj)})
    if rdfs_labels:
        return rdfs_labels[0]
    metaqa_labels = sorted({str(obj) for obj in labels.objects(node, METAQA_LABEL_PRED) if str(obj)})
    if metaqa_labels:
        return metaqa_labels[0]
    return ""


def local_schema_from_csv_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = (
            int(row["rank"]),
            int(row["hopCount"]),
            row["direction"],
            row["property"],
            int(row["frequency"]),
        )
        slot = grouped.setdefault(
            key,
            {
                "rank": key[0],
                "hopCount": key[1],
                "direction": key[2],
                "property": key[3],
                "frequency": key[4],
                "_neighbors": {},
                "_literals": set(),
            },
        )
        neighbor = row.get("exampleNeighbor", "")
        label = row.get("exampleNeighborLabel", "")
        if neighbor:
            prev = slot["_neighbors"].get(neighbor, "")
            if label or not prev:
                slot["_neighbors"][neighbor] = label
        literal = row.get("exampleLiteral", "")
        if literal:
            slot["_literals"].add(literal)

    normalized: list[dict[str, Any]] = []
    for slot in grouped.values():
        normalized.append(
            {
                "rank": slot["rank"],
                "hopCount": slot["hopCount"],
                "direction": slot["direction"],
                "property": slot["property"],
                "frequency": slot["frequency"],
                "exampleNeighbors": [
                    {"entity": entity, "label": label}
                    for entity, label in sorted(slot["_neighbors"].items())
                ],
                "exampleLiterals": sorted(slot["_literals"]),
            }
        )
    normalized.sort(key=lambda row: (row["rank"], row["hopCount"], row["direction"], row["property"]))
    return normalized


def build_local_schema_profile(
    source: Graph,
    entity: str,
    hops: int,
    direction: str,
    max_examples: int,
    label_source: Graph | None = None,
) -> list[dict[str, Any]]:
    center = URIRef(entity)
    hop_limit = max(1, hops)
    mode = direction.lower().strip() or "both"
    if mode not in {"out", "in", "both"}:
        mode = "both"
    example_cap = max(1, max_examples)

    slots: dict[tuple[int, str, str], dict[str, Any]] = {}
    seen_depth: dict[URIRef, int] = {center: 0}
    queue: deque[tuple[URIRef, int]] = deque([(center, 0)])

    while queue:
        node, depth = queue.popleft()
        if depth >= hop_limit:
            continue

        if mode in {"out", "both"}:
            outgoing = sorted(
                source.triples((node, None, None)),
                key=lambda triple: (str(triple[1]), str(triple[2])),
            )
            for _, pred, obj in outgoing:
                key = (depth + 1, "out", str(pred))
                slot = slots.setdefault(
                    key,
                    {
                        "hopCount": depth + 1,
                        "direction": "out",
                        "property": str(pred),
                        "frequency": 0,
                        "neighbor_examples": [],
                        "literal_examples": [],
                    },
                )
                slot["frequency"] += 1
                if isinstance(obj, URIRef):
                    if obj not in slot["neighbor_examples"] and len(slot["neighbor_examples"]) < example_cap:
                        slot["neighbor_examples"].append(obj)
                    next_depth = depth + 1
                    prev = seen_depth.get(obj)
                    if prev is None or next_depth < prev:
                        seen_depth[obj] = next_depth
                        queue.append((obj, next_depth))
                else:
                    value = str(obj)
                    if value not in slot["literal_examples"] and len(slot["literal_examples"]) < example_cap:
                        slot["literal_examples"].append(value)

        if mode in {"in", "both"}:
            incoming = sorted(
                source.triples((None, None, node)),
                key=lambda triple: (str(triple[1]), str(triple[0])),
            )
            for subj, pred, _ in incoming:
                key = (depth + 1, "in", str(pred))
                slot = slots.setdefault(
                    key,
                    {
                        "hopCount": depth + 1,
                        "direction": "in",
                        "property": str(pred),
                        "frequency": 0,
                        "neighbor_examples": [],
                        "literal_examples": [],
                    },
                )
                slot["frequency"] += 1
                if isinstance(subj, URIRef):
                    if subj not in slot["neighbor_examples"] and len(slot["neighbor_examples"]) < example_cap:
                        slot["neighbor_examples"].append(subj)
                    next_depth = depth + 1
                    prev = seen_depth.get(subj)
                    if prev is None or next_depth < prev:
                        seen_depth[subj] = next_depth
                        queue.append((subj, next_depth))

    normalized: list[dict[str, Any]] = []
    ordered = sorted(slots.values(), key=lambda slot: (slot["hopCount"], slot["direction"], slot["property"]))
    for rank, slot in enumerate(ordered, start=1):
        normalized.append(
            {
                "rank": rank,
                "hopCount": slot["hopCount"],
                "direction": slot["direction"],
                "property": slot["property"],
                "frequency": slot["frequency"],
                "exampleNeighbors": [
                    {"entity": str(node), "label": label_for(source, node, label_source)}
                    for node in sorted(slot["neighbor_examples"], key=str)
                ],
                "exampleLiterals": sorted(slot["literal_examples"]),
            }
        )
    return normalized


@dataclass
class SideResult:
    normalized_output: Any
    metrics: dict[str, Any]


@dataclass(frozen=True)
class MetaQAQuestion:
    qid: str
    question_text: str
    anchor_label: str
    anchor_entity: str
    answer_relation: str
    gold_answers: tuple[str, ...]


def make_ggf_result(
    query: str,
    normalized_output: Any,
    wall_time_s: float,
    transfer_definition: str,
    http_metrics: HttpMetrics | None = None,
) -> SideResult:
    if http_metrics is not None:
        return SideResult(
            normalized_output=normalized_output,
            metrics=ggf_http_result_metrics(
                http_metrics,
                normalized_output,
                wall_time_s,
                f"HTTP GGF request/response bytes + normalized result bytes ({transfer_definition})",
            ),
        )

    output_bytes = canonical_json_bytes(normalized_output)
    return SideResult(
        normalized_output=normalized_output,
        metrics={
            "wall_time_s": round(wall_time_s, 6),
            "logical_call_count": 1,
            "upload_bytes": len(query.encode("utf-8")),
            "download_bytes": output_bytes,
            "output_bytes": output_bytes,
            "transfer_total_bytes": len(query.encode("utf-8")) + output_bytes,
            "transfer_definition": transfer_definition,
        },
    )


def local_script_metrics(args: argparse.Namespace, normalized_output: Any, wall_time_s: float, note: str) -> dict[str, Any]:
    input_bytes = Path(args.graph).stat().st_size
    output_bytes = canonical_json_bytes(normalized_output)
    return {
        "wall_time_s": round(wall_time_s, 6),
        "logical_call_count": 1,
        "upload_bytes": 0,
        "download_bytes": input_bytes,
        "output_bytes": output_bytes,
        "transfer_total_bytes": input_bytes + output_bytes,
        "transfer_definition": note,
    }


def qid_sort_key(qid: str) -> tuple[int, str]:
    suffix = qid[1:] if qid.startswith("q") else qid
    return (int(suffix), qid) if suffix.isdigit() else (10**9, qid)


def load_metaqa_questions(args: argparse.Namespace) -> tuple[Graph, list[MetaQAQuestion]]:
    log_progress(f"[metaqa] loading KB from {args.metaqa_kb}")
    kb = load_local_graph(args.metaqa_kb, "turtle")
    log_progress(f"[metaqa] loading QA from {args.metaqa_qa}")
    qa = load_local_graph(args.metaqa_qa, "turtle")
    id_pred = URIRef(f"{MQQA}id")
    text_pred = URIRef(f"{MQQA}text")
    gold_pred = URIRef(f"{MQQA}goldAnswer")

    raw_questions: list[tuple[str, str, tuple[str, ...]]] = []
    for quri, _, qid_term in qa.triples((None, id_pred, None)):
        qid = str(qid_term)
        text = next((str(obj) for obj in qa.objects(quri, text_pred)), "")
        gold_answers = tuple(str(obj) for obj in qa.objects(quri, gold_pred))
        if not text or not gold_answers:
            continue
        raw_questions.append((qid, text, gold_answers))

    raw_questions.sort(key=lambda item: qid_sort_key(item[0]))
    if args.metaqa_limit > 0:
        raw_questions = raw_questions[: args.metaqa_limit]

    questions: list[MetaQAQuestion] = []
    for qid, text, gold_answers in raw_questions:
        anchor_label = extract_anchor_bracket(text)
        answer_relation = infer_metaqa_answer_relation(text)
        anchor_entity, _ = find_metaqa_anchor(kb, anchor_label)
        if not anchor_entity or not answer_relation:
            continue
        questions.append(
            MetaQAQuestion(
                qid=qid,
                question_text=text,
                anchor_label=anchor_label,
                anchor_entity=anchor_entity,
                answer_relation=answer_relation,
                gold_answers=gold_answers,
            )
        )
    log_progress(f"[metaqa] prepared {len(questions)} usable question(s)")
    return kb, questions


def sparql_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def batched(items: list[MetaQAQuestion], size: int) -> list[list[MetaQAQuestion]]:
    if size <= 0:
        raise ValueError("metaqa_batch_size must be > 0")
    out: list[list[MetaQAQuestion]] = []
    it = iter(items)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            return out
        out.append(chunk)


def build_metaqa_2hop_query(args: argparse.Namespace, questions: list[MetaQAQuestion]) -> str:
    if not questions:
        raise ValueError("No MetaQA questions available for evaluation.")
    branches = []
    for question in questions:
        qid = sparql_quote(question.qid)
        anchor = question.anchor_entity
        answer_rel = question.answer_relation
        branches.append(
            f'''  {{
    BIND("{qid}" AS ?qid)
    BIND(ggf:EXPAND(<{anchor}>, {args.metaqa_hops}, "{args.metaqa_direction}") AS ?gExp)
    OPTIONAL {{
      GRAPH ?gExp {{
        {{
          {{ <{anchor}> ?bridge ?mid . FILTER(isIRI(?mid)) }}
          UNION
          {{ ?mid ?bridge <{anchor}> . FILTER(isIRI(?mid)) }}
        }}
        {{
          {{ ?mid <{answer_rel}> ?cand . FILTER(?cand != <{anchor}>) }}
          UNION
          {{ ?cand <{answer_rel}> ?mid . FILTER(?cand != <{anchor}>) }}
        }}
      }}
      BIND(STR(?cand) AS ?answerValue)
    }}
  }}'''
        )

    union_body = "\n  UNION\n".join(branches)
    return f'''PREFIX ggf: <http://ggf.org/>
SELECT DISTINCT ?qid ?answerValue WHERE {{
{union_body}
}}
ORDER BY ?qid ?answerValue
'''


def build_metaqa_anchor_search_rerank_query(args: argparse.Namespace, questions: list[MetaQAQuestion]) -> str:
    if not questions:
        raise ValueError("No MetaQA questions available for anchor search/rerank evaluation.")
    rows = []
    index_dir = sparql_quote(str(Path(args.metaqa_anchor_faiss_dir).resolve()))
    for question in questions:
        rows.append(
            f'    ("{sparql_quote(question.qid)}" "{sparql_quote(question.question_text)}" '
            f'"{sparql_quote(question.anchor_label)}" <{question.anchor_entity}>)'
        )
    values = "\n".join(rows)
    return f'''PREFIX ggf: <http://ggf.org/>
PREFIX cand: <http://example.org/cand#>
SELECT ?qid ?goldEntity ?entity ?label ?rank ?originalPosition ?searchScore ?confidence ?reason WHERE {{
  VALUES (?qid ?questionText ?anchorLabel ?goldEntity) {{
{values}
  }}
  BIND(ggf:METAQA-SEARCH-FAISS(?anchorLabel, {args.anchor_search_top_k}, "{index_dir}") AS ?gSearch)
  BIND(ggf:METAQA-RERANK-LOCAL(?questionText, ?gSearch) AS ?gRank)
  GRAPH ?gRank {{
    ?node a cand:RerankedEntity ;
          cand:entity ?entity ;
          cand:label ?label ;
          cand:rank ?rank ;
          cand:originalPosition ?originalPosition ;
          cand:searchScore ?searchScore ;
          cand:confidence ?confidence ;
          cand:reason ?reason .
  }}
}}
ORDER BY ?qid ?rank
'''


def normalize_metaqa_anchor_rankings(
    questions: list[MetaQAQuestion],
    ranked_by_qid: dict[str, list[dict[str, Any]]],
    output_top_k: int,
) -> list[dict[str, Any]]:
    by_qid = {question.qid: question for question in questions}
    normalized: list[dict[str, Any]] = []
    for question in questions:
        ranked = sorted(ranked_by_qid.get(question.qid, []), key=lambda row: (int(row["rank"]), row["entity"]))
        gold_rank = None
        for row in ranked:
            if row["entity"] == question.anchor_entity:
                gold_rank = int(row["rank"])
                break
        reciprocal_rank = 0.0 if gold_rank is None else round(1.0 / float(gold_rank), 6)
        normalized.append(
            {
                "qid": question.qid,
                "question_text": question.question_text,
                "anchor_label": question.anchor_label,
                "gold_entity": question.anchor_entity,
                "candidate_count": len(ranked),
                "gold_rank": gold_rank,
                "top1_correct": gold_rank == 1,
                "reciprocal_rank": reciprocal_rank,
                "top_candidates": [
                    {
                        "entity": row["entity"],
                        "label": row.get("label", ""),
                        "rank": int(row["rank"]),
                        "originalPosition": int(row.get("originalPosition", row["rank"])),
                        "searchScore": round(float(row.get("searchScore", row.get("score", 0.0))), 6),
                        "confidence": round(float(row.get("confidence", 0.0)), 6),
                        "reason": row.get("reason", ""),
                    }
                    for row in ranked[:output_top_k]
                ],
            }
        )
    return normalized


def normalize_metaqa_outputs(
    questions: list[MetaQAQuestion],
    predicted_by_qid: dict[str, list[str]],
    kb: Graph,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for question in questions:
        predicted_values = sorted({value for value in predicted_by_qid.get(question.qid, []) if value})
        predicted_tokens = metaqa_predicted_answer_tokens(predicted_values)
        gold_groups = metaqa_gold_answer_token_groups(kb, list(question.gold_answers))
        matched_gold_answers = [
            answer
            for answer, accepted_tokens in gold_groups
            if predicted_tokens & accepted_tokens
        ]
        gold_count = len(gold_groups)
        matched_count = len(matched_gold_answers)
        recall = 1.0 if gold_count == 0 else round(matched_count / float(gold_count), 6)
        normalized.append(
            {
                "qid": question.qid,
                "question_text": question.question_text,
                "anchor_label": question.anchor_label,
                "anchor_entity": question.anchor_entity,
                "answer_relation": question.answer_relation,
                "gold_answers": list(question.gold_answers),
                "predicted_values": predicted_values,
                "candidate_count": len(predicted_values),
                "matched_gold_answers": matched_gold_answers,
                "matched_gold_count": matched_count,
                "gold_count": gold_count,
                "gold_recall": recall,
                "has_any_gold_match": matched_count > 0,
                "all_gold_matched": matched_count == gold_count,
            }
        )
    return normalized


def comparison_view(case_name: str, normalized_output: Any) -> Any:
    if case_name != "metaqa_anchor_search_rerank_local":
        return normalized_output
    if not isinstance(normalized_output, list):
        return normalized_output
    reduced: list[dict[str, Any]] = []
    for row in normalized_output:
        if not isinstance(row, dict):
            reduced.append(row)
            continue
        reduced.append(
            {
                "qid": row.get("qid"),
                "gold_entity": row.get("gold_entity"),
                "gold_rank": row.get("gold_rank"),
                "top1_correct": row.get("top1_correct"),
                "reciprocal_rank": row.get("reciprocal_rank"),
                "top_candidates": [
                    {
                        "entity": candidate.get("entity"),
                        "rank": candidate.get("rank"),
                        "originalPosition": candidate.get("originalPosition"),
                    }
                    for candidate in row.get("top_candidates", [])
                    if isinstance(candidate, dict)
                ],
            }
        )
    return reduced


def case_expand_ggf(args: argparse.Namespace) -> SideResult:
    query = build_expand_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = triples_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_expand_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        src = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        expanded = expand_neighborhood_graph(src, [args.entity], args.hops, args.direction)
        elapsed = time.perf_counter() - t0
        normalized = sorted([[str(s), str(p), str(o)] for s, p, o in expanded])
        return SideResult(normalized, local_script_metrics(args, normalized, elapsed, "full source graph bytes + normalized result bytes"))

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    expanded = http_expand_neighborhood_graph(client, [args.entity], args.hops, args.direction)
    elapsed = time.perf_counter() - t0
    normalized = sorted([[str(s), str(p), str(o)] for s, p, o in expanded])
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP neighborhood retrieval bytes + normalized result bytes"),
    )


def case_paths_ggf(args: argparse.Namespace) -> SideResult:
    query = build_paths_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = canonicalize_paths_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_paths_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        src = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        paths = shortest_paths(src, args.start, args.goal, args.max_depth, args.direction, args.max_paths)
        elapsed = time.perf_counter() - t0
        normalized = [
            [{"src": str(s), "pred": str(p), "dst": str(o)} for (s, p, o) in path]
            for path in paths
        ]
        normalized.sort(key=lambda path: tuple((step["src"], step["pred"], step["dst"]) for step in path))
        return SideResult(normalized, local_script_metrics(args, normalized, elapsed, "full source graph bytes + normalized result bytes"))

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    neighborhood = http_expand_neighborhood_graph(client, [args.start], args.max_depth, args.direction)
    paths = shortest_paths(neighborhood, args.start, args.goal, args.max_depth, args.direction, args.max_paths)
    elapsed = time.perf_counter() - t0
    normalized = [
        [{"src": str(s), "pred": str(p), "dst": str(o)} for (s, p, o) in path]
        for path in paths
    ]
    normalized.sort(key=lambda path: tuple((step["src"], step["pred"], step["dst"]) for step in path))
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP path-neighborhood retrieval bytes + normalized result bytes"),
    )


def case_simrank_ggf(args: argparse.Namespace) -> SideResult:
    query = build_simrank_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = ranking_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_simrank_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        src = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        ranking = simrank_ranking(src, args.center, args.decay, args.max_iter, args.top_k, args.max_nodes)
        elapsed = time.perf_counter() - t0
        normalized = [{"rank": i + 1, "entity": entity, "score": score} for i, (entity, score) in enumerate(ranking)]
        return SideResult(normalized, local_script_metrics(args, normalized, elapsed, "full source graph bytes + normalized result bytes"))

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    src = http_build_simrank_graph_naive(client, args.center, args.max_nodes)
    ranking = simrank_ranking(src, args.center, args.decay, args.max_iter, args.top_k, args.max_nodes)
    elapsed = time.perf_counter() - t0
    normalized = [{"rank": i + 1, "entity": entity, "score": score} for i, (entity, score) in enumerate(ranking)]
    return SideResult(
        normalized,
        script_http_metrics(
            client,
            normalized,
            elapsed,
            "HTTP center-driven per-node neighborhood retrieval bytes + normalized result bytes",
        ),
    )


def case_random_sample_ggf(args: argparse.Namespace) -> SideResult:
    query = build_random_sample_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = random_sample_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "single query input bytes + normalized random-sample result bytes", http_metrics)


def case_random_sample_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        result = random_sample_neighborhood(
            source,
            args.entity,
            args.hops,
            args.direction,
            args.sample_rate,
            args.seed,
        )
        elapsed = time.perf_counter() - t0
        normalized = {
            "metadata": {
                "sampleRate": result.sample_rate,
                "exactTripleCount": result.exact_triple_count,
                "sampledTripleCount": result.sampled_triple_count,
                "estimatedTripleCount": result.estimated_triple_count,
                "absoluteError": result.absolute_error,
                "relativeError": result.relative_error,
            },
            "predicateStats": [
                {
                    "rank": idx,
                    "property": stat.property_iri,
                    "exactFrequency": stat.exact_frequency,
                    "sampledFrequency": stat.sampled_frequency,
                    "estimatedFrequency": stat.estimated_frequency,
                    "absoluteError": stat.absolute_error,
                    "relativeError": stat.relative_error,
                }
                for idx, stat in enumerate(result.predicate_estimates, start=1)
            ],
        }
        return SideResult(
            normalized,
            local_script_metrics(
                args,
                normalized,
                elapsed,
                "full source graph bytes + sampled neighborhood and cardinality estimate result bytes",
            ),
        )

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    local_graph = http_expand_neighborhood_graph_naive(client, [args.entity], args.hops, args.direction)
    result = random_sample_neighborhood(local_graph, args.entity, args.hops, args.direction, args.sample_rate, args.seed)
    elapsed = time.perf_counter() - t0
    normalized = {
        "metadata": {
            "sampleRate": result.sample_rate,
            "exactTripleCount": result.exact_triple_count,
            "sampledTripleCount": result.sampled_triple_count,
            "estimatedTripleCount": result.estimated_triple_count,
            "absoluteError": result.absolute_error,
            "relativeError": result.relative_error,
        },
        "predicateStats": [
            {
                "rank": idx,
                "property": stat.property_iri,
                "exactFrequency": stat.exact_frequency,
                "sampledFrequency": stat.sampled_frequency,
                "estimatedFrequency": stat.estimated_frequency,
                "absoluteError": stat.absolute_error,
                "relativeError": stat.relative_error,
            }
            for idx, stat in enumerate(result.predicate_estimates, start=1)
        ],
    }
    return SideResult(
        normalized,
        script_http_metrics(
            client,
            normalized,
            elapsed,
            "HTTP predicate-discovery and per-predicate neighborhood retrieval bytes + normalized cardinality estimate result bytes",
        ),
    )


def case_local_schema_ggf(args: argparse.Namespace) -> SideResult:
    query = build_local_schema_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = local_schema_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_local_schema_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        local_graph = expand_neighborhood_graph(source, [args.entity], args.schema_hops, args.direction)
        t0 = time.perf_counter()
        normalized = build_local_schema_profile(
            source,
            args.entity,
            args.schema_hops,
            args.direction,
            args.schema_max_examples,
        )
        elapsed = time.perf_counter() - t0

        label_support = Graph()
        seen_label_nodes: set[str] = set()
        for row in normalized:
            for neighbor in row["exampleNeighbors"]:
                entity = neighbor["entity"]
                if entity in seen_label_nodes:
                    continue
                seen_label_nodes.add(entity)
                node = URIRef(entity)
                rdfs_label = next(source.objects(node, RDFS.label), None)
                if rdfs_label is not None:
                    label_support.add((node, RDFS.label, rdfs_label))
                    continue
                metaqa_label = next(source.objects(node, METAQA_LABEL_PRED), None)
                if metaqa_label is not None:
                    label_support.add((node, METAQA_LABEL_PRED, metaqa_label))

        output_bytes = canonical_json_bytes(normalized)
        transfer_bytes = graph_serialized_bytes(local_graph) + graph_serialized_bytes(label_support)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": 1,
                "upload_bytes": 0,
                "download_bytes": transfer_bytes,
                "output_bytes": output_bytes,
                "transfer_total_bytes": transfer_bytes + output_bytes,
                "transfer_definition": "serialized expanded local neighborhood bytes + supporting label triples + normalized local schema result bytes",
            },
        )

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    local_graph = http_expand_neighborhood_graph(client, [args.entity], args.schema_hops, args.direction)
    label_nodes = {str(node) for node in local_graph.subjects() if isinstance(node, URIRef)}
    label_nodes.update(str(node) for node in local_graph.objects() if isinstance(node, URIRef))
    label_support = http_fetch_labels_graph(client, sorted(label_nodes))
    label_index = Graph()
    for triple in local_graph:
        label_index.add(triple)
    for triple in label_support:
        label_index.add(triple)
    normalized = build_local_schema_profile(
        local_graph,
        args.entity,
        args.schema_hops,
        args.direction,
        args.schema_max_examples,
        label_source=label_index,
    )
    elapsed = time.perf_counter() - t0
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP neighborhood and label retrieval bytes + normalized local schema result bytes"),
    )


def case_cbd_esbm_ggf(args: argparse.Namespace) -> SideResult:
    query = build_cbd_esbm_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = summary_rows_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_cbd_esbm_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        candidates = metaqa_candidate_pool(source, args.ref_entity, args.candidate_limit)
        candidate_bytes = canonical_json_bytes(candidates)
        rows: list[dict[str, str]] = []
        download = candidate_bytes
        calls = 1 + len(candidates)
        for cand in candidates:
            local_graph = local_cbd_graph(source, cand["entity"])
            download += graph_serialized_bytes(local_graph)
            triples = select_summary_triples(local_graph, cand["entity"], args.k, args.neighborhood, args.mode, args.seed)
            for s, p, o in triples:
                rows.append(
                    {
                        "entity": cand["entity"],
                        "entityLabel": cand["entityLabel"],
                        "s": str(s),
                        "p": str(p),
                        "o": str(o),
                    }
                )
        elapsed = time.perf_counter() - t0
        normalized = sorted(rows, key=lambda row: (row["entityLabel"], row["s"], row["p"], row["o"]))
        output_bytes = canonical_json_bytes(normalized)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": calls,
                "upload_bytes": 0,
                "download_bytes": download,
                "output_bytes": output_bytes,
                "transfer_total_bytes": download + output_bytes,
                "transfer_definition": "candidate pool bytes + serialized CBD bytes for cohort entities + normalized result bytes",
            },
        )

    client = reset_http_metrics(args)
    t0 = time.perf_counter()
    query = f"""SELECT ?entity ?entityLabel WHERE {{
  ?entity <{MREL}release_year> ?year .
  FILTER(?entity != <{args.ref_entity}>)
  BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)
}} ORDER BY ?entityLabel LIMIT {args.candidate_limit}"""
    candidate_rows = client.select(query)
    candidates = [
        {"entity": str(row["entity"]), "entityLabel": str(row["entityLabel"])}
        for row in candidate_rows
    ]
    rows: list[dict[str, str]] = []
    for cand in candidates:
        local_graph = http_fetch_cbd_graph(client, cand["entity"])
        triples = select_summary_triples(local_graph, cand["entity"], args.k, args.neighborhood, args.mode, args.seed)
        for s, p, o in triples:
            rows.append(
                {
                    "entity": cand["entity"],
                    "entityLabel": cand["entityLabel"],
                    "s": str(s),
                    "p": str(p),
                    "o": str(o),
                }
            )
    elapsed = time.perf_counter() - t0
    normalized = sorted(rows, key=lambda row: (row["entityLabel"], row["s"], row["p"], row["o"]))
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP candidate pool and CBD retrieval bytes + normalized result bytes"),
    )


def case_entity_similarity_ggf(args: argparse.Namespace) -> SideResult:
    query = build_entity_similarity_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = [
        {
            "entity": row["entity"],
            "entityLabel": row["entityLabel"],
            "score": float(row["score"]),
            "shared": int(row["shared"]),
            "differing": int(row["differing"]),
            "exclusive": int(row["exclusive"]),
        }
        for row in rows
    ]
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_entity_similarity_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        candidates = metaqa_candidate_pool(source, args.ref_entity, args.candidate_limit)
        candidate_bytes = canonical_json_bytes(candidates)

        calls = 2 + len(candidates)
        upload = 0

        ref_cbd = local_cbd_graph(source, args.ref_entity)
        download = candidate_bytes + graph_serialized_bytes(ref_cbd)
        ref_sum = Graph()
        for triple in select_summary_triples(ref_cbd, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed):
            ref_sum.add(triple)

        rows: list[dict[str, Any]] = []
        for cand in candidates:
            ent_cbd = local_cbd_graph(source, cand["entity"])
            download += graph_serialized_bytes(ent_cbd)
            ent_sum = Graph()
            for triple in select_summary_triples(ent_cbd, cand["entity"], args.k, args.neighborhood, args.mode, args.seed):
                ent_sum.add(triple)
            cmp = compare_centered_graphs(ref_sum, ent_sum, args.ref_entity, cand["entity"])
            rows.append(
                {
                    "entity": cand["entity"],
                    "entityLabel": cand["entityLabel"],
                    "score": cmp.similarity_score,
                    "shared": cmp.shared_count,
                    "differing": cmp.differing_count,
                    "exclusive": cmp.exclusive_count,
                }
            )

        rows.sort(key=lambda r: (-float(r["score"]), -int(r["shared"]), str(r["entityLabel"])))
        normalized = rows[: args.top]
        elapsed = time.perf_counter() - t0
        output_bytes = canonical_json_bytes(normalized)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": calls,
                "upload_bytes": upload,
                "download_bytes": download,
                "output_bytes": output_bytes,
                "transfer_total_bytes": upload + download + output_bytes,
                "transfer_definition": "candidate pool bytes + serialized CBD bytes for reference and candidates + normalized result bytes",
            },
        )

    client = reset_http_metrics(args)
    query = f"""SELECT ?entity WHERE {{
  ?entity <{MREL}release_year> ?year .
  FILTER(?entity != <{args.ref_entity}>)
}} ORDER BY ?entity LIMIT {args.candidate_limit}"""
    t0 = time.perf_counter()
    candidate_rows = client.select(query)
    candidates = [
        {"entity": str(row["entity"]), "entityLabel": str(row["entity"]).rsplit("/", 1)[-1]}
        for row in candidate_rows
    ]
    ref_cbd = http_fetch_cbd_graph(client, args.ref_entity)
    ref_sum = Graph()
    for triple in select_summary_triples(ref_cbd, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed):
        ref_sum.add(triple)
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        ent_cbd = http_fetch_cbd_graph(client, cand["entity"])
        ent_sum = Graph()
        for triple in select_summary_triples(ent_cbd, cand["entity"], args.k, args.neighborhood, args.mode, args.seed):
            ent_sum.add(triple)
        cmp = compare_centered_graphs(ref_sum, ent_sum, args.ref_entity, cand["entity"])
        rows.append(
            {
                "entity": cand["entity"],
                "entityLabel": cand["entityLabel"],
                "score": cmp.similarity_score,
                "shared": cmp.shared_count,
                "differing": cmp.differing_count,
                "exclusive": cmp.exclusive_count,
            }
        )
    rows.sort(key=lambda r: (-float(r["score"]), -int(r["shared"]), str(r["entityLabel"])))
    normalized = rows[: args.top]
    elapsed = time.perf_counter() - t0
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP candidate pool and CBD retrieval bytes + normalized result bytes"),
    )


def case_entity_similarity_score_only_ggf(args: argparse.Namespace) -> SideResult:
    query = build_entity_similarity_score_only_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = [
        {
            "entity": row["entity"],
            "score": float(row["score"]),
        }
        for row in rows
    ]
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_entity_similarity_score_only_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        candidates = metaqa_candidate_pool(
            source,
            args.ref_entity,
            args.score_only_candidate_limit,
            release_year_filter=args.score_only_candidate_year,
        )
        candidate_bytes = canonical_json_bytes(candidates)

        calls = 2 + len(candidates)
        upload = 0

        ref_cbd = local_cbd_graph(source, args.ref_entity)
        download = candidate_bytes + graph_serialized_bytes(ref_cbd)
        ref_sum = Graph()
        for triple in select_summary_triples(ref_cbd, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed):
            ref_sum.add(triple)

        rows: list[dict[str, Any]] = []
        for cand in candidates:
            ent_cbd = local_cbd_graph(source, cand["entity"])
            download += graph_serialized_bytes(ent_cbd)
            ent_sum = Graph()
            for triple in select_summary_triples(ent_cbd, cand["entity"], args.k, args.neighborhood, args.mode, args.seed):
                ent_sum.add(triple)
            cmp = compare_centered_graphs(ref_sum, ent_sum, args.ref_entity, cand["entity"])
            rows.append(
                {
                    "entity": cand["entity"],
                    "score": cmp.similarity_score,
                }
            )

        rows.sort(key=lambda r: (-float(r["score"]), str(r["entity"])))
        normalized = rows[: args.top]
        elapsed = time.perf_counter() - t0
        output_bytes = canonical_json_bytes(normalized)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": calls,
                "upload_bytes": upload,
                "download_bytes": download,
                "output_bytes": output_bytes,
                "transfer_total_bytes": upload + download + output_bytes,
                "transfer_definition": "candidate pool bytes + serialized CBD bytes for reference and candidates + normalized result bytes",
            },
        )

    client = reset_http_metrics(args)
    query = f"""SELECT ?entity WHERE {{
  ?entity <{MREL}release_year> {args.score_only_candidate_year} .
  FILTER(?entity != <{args.ref_entity}>)
}} ORDER BY ?entity LIMIT {args.score_only_candidate_limit}"""
    t0 = time.perf_counter()
    candidate_rows = client.select(query)
    candidates = [{"entity": str(row["entity"])} for row in candidate_rows]
    ref_cbd = http_fetch_cbd_graph(client, args.ref_entity)
    ref_sum = Graph()
    for triple in select_summary_triples(ref_cbd, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed):
        ref_sum.add(triple)
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        ent_cbd = http_fetch_cbd_graph(client, cand["entity"])
        ent_sum = Graph()
        for triple in select_summary_triples(ent_cbd, cand["entity"], args.k, args.neighborhood, args.mode, args.seed):
            ent_sum.add(triple)
        cmp = compare_centered_graphs(ref_sum, ent_sum, args.ref_entity, cand["entity"])
        rows.append(
            {
                "entity": cand["entity"],
                "score": cmp.similarity_score,
            }
        )
    rows.sort(key=lambda r: (-float(r["score"]), str(r["entity"])))
    normalized = rows[: args.top]
    elapsed = time.perf_counter() - t0
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP candidate pool and CBD retrieval bytes + normalized result bytes"),
    )


def case_entity_typing_ggf(args: argparse.Namespace) -> SideResult:
    query = build_entity_typing_query(args)
    rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.graph, load_format=args.format)
    normalized = typing_rows_from_csv_rows(rows)
    return make_ggf_result(query, normalized, elapsed, "query input bytes + normalized result bytes", http_metrics)


def case_entity_typing_script(args: argparse.Namespace) -> SideResult:
    if args.script_access == "local":
        source = load_local_graph(args.graph, args.format)
        t0 = time.perf_counter()
        candidates = metaqa_candidate_pool(source, args.ref_entity, args.candidate_limit)
        candidate_bytes = canonical_json_bytes(candidates)
        download = candidate_bytes
        rows: list[dict[str, str]] = []
        for cand in candidates:
            cbd = local_cbd_graph(source, cand["entity"])
            download += graph_serialized_bytes(cbd)
            context_text = graph_to_text(cbd)
            prompt = build_entity_typing_prompt(cand["entityLabel"], context_text)
            g_llm = _alias_llm(prompt)
            if g_llm is None:
                continue
            rows.extend(typing_rows_from_graph(cand["entity"], cand["entityLabel"], UDF_STORE.get_context(g_llm)))
        elapsed = time.perf_counter() - t0
        normalized = sorted(rows, key=lambda row: (row["entityLabel"], row["predictedType"], row["justification"]))
        output_bytes = canonical_json_bytes(normalized)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": 1 + len(candidates) + len(candidates),
                "upload_bytes": 0,
                "download_bytes": download,
                "output_bytes": output_bytes,
                "transfer_total_bytes": download + output_bytes,
                "transfer_definition": "candidate pool bytes + serialized CBD bytes for cohort entities + normalized result bytes",
            },
        )

    client = reset_http_metrics(args)
    query = f"""SELECT ?entity ?entityLabel WHERE {{
  ?entity <{MREL}release_year> ?year .
  FILTER(?entity != <{args.ref_entity}>)
  BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)
}} ORDER BY ?entityLabel LIMIT {args.candidate_limit}"""
    t0 = time.perf_counter()
    candidate_rows = client.select(query)
    candidates = [
        {"entity": str(row["entity"]), "entityLabel": str(row["entityLabel"])}
        for row in candidate_rows
    ]
    rows: list[dict[str, str]] = []
    for cand in candidates:
        cbd = http_fetch_cbd_graph(client, cand["entity"])
        context_text = graph_to_text(cbd)
        prompt = build_entity_typing_prompt(cand["entityLabel"], context_text)
        g_llm = _alias_llm(prompt)
        if g_llm is None:
            continue
        rows.extend(typing_rows_from_graph(cand["entity"], cand["entityLabel"], UDF_STORE.get_context(g_llm)))
    elapsed = time.perf_counter() - t0
    normalized = sorted(rows, key=lambda row: (row["entityLabel"], row["predictedType"], row["justification"]))
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP candidate pool and CBD retrieval bytes + normalized result bytes"),
    )


def case_metaqa_2hop_local_ggf(args: argparse.Namespace) -> SideResult:
    kb, questions = load_metaqa_questions(args)
    batches = batched(questions, args.metaqa_batch_size)
    log_progress(f"[metaqa][ggf] running {len(batches)} batch(es) of up to {args.metaqa_batch_size} question(s)")
    rows: list[dict[str, str]] = []
    total_elapsed = 0.0
    total_upload_bytes = 0
    total_http_metrics = HttpMetrics()
    for batch_index, batch in enumerate(batches, start=1):
        qid_start = batch[0].qid
        qid_end = batch[-1].qid
        log_progress(f"[metaqa][ggf] batch {batch_index}/{len(batches)}: {qid_start}..{qid_end}")
        query = build_metaqa_2hop_query(args, batch)
        batch_rows, elapsed, http_metrics = run_ggf_query(args, query, load_path=args.metaqa_kb, load_format="turtle")
        rows.extend(batch_rows)
        total_elapsed += elapsed
        if http_metrics is None:
            total_upload_bytes += len(query.encode("utf-8"))
        else:
            add_http_metrics(total_http_metrics, http_metrics)
        log_progress(
            f"[metaqa][ggf] batch {batch_index}/{len(batches)} done in {elapsed:.3f}s with {len(batch_rows)} row(s)"
        )
    predicted_by_qid: dict[str, list[str]] = {}
    for row in rows:
        qid = row.get("qid", "")
        answer_value = row.get("answerValue", "")
        predicted_by_qid.setdefault(qid, [])
        if answer_value:
            predicted_by_qid[qid].append(answer_value)
    normalized = normalize_metaqa_outputs(questions, predicted_by_qid, kb)
    output_bytes = canonical_json_bytes(normalized)
    if args.ggf_access == "http":
        return SideResult(
            normalized_output=normalized,
            metrics=ggf_http_result_metrics(
                total_http_metrics,
                normalized,
                total_elapsed,
                "sum of batched HTTP GGF request/response bytes + compact answer candidates per question",
            ),
        )
    return SideResult(
        normalized_output=normalized,
        metrics={
            "wall_time_s": round(total_elapsed, 6),
            "logical_call_count": len(batches),
            "upload_bytes": total_upload_bytes,
            "download_bytes": output_bytes,
            "output_bytes": output_bytes,
            "transfer_total_bytes": total_upload_bytes + output_bytes,
            "transfer_definition": "sum of batched query input bytes + compact answer candidates per question",
        },
    )


def case_metaqa_2hop_local_script(args: argparse.Namespace) -> SideResult:
    kb, questions = load_metaqa_questions(args)
    predicted_by_qid: dict[str, list[str]] = {}
    t0 = time.perf_counter()
    if args.script_access == "local":
        shipped_bytes = 0
        calls = 0
        log_progress(f"[metaqa][script] expanding {len(questions)} question(s)")
        for question in questions:
            expanded = expand_neighborhood_graph(
                kb,
                [question.anchor_entity],
                args.metaqa_hops,
                args.metaqa_direction,
            )
            shipped_bytes += graph_serialized_bytes(expanded)
            calls += 1
            predicted_by_qid[question.qid] = metaqa_answer_terms_from_graph(
                expanded,
                question.anchor_entity,
                question.answer_relation,
            )
            if calls % 25 == 0 or calls == len(questions):
                log_progress(f"[metaqa][script] processed {calls}/{len(questions)} question(s)")
        elapsed = time.perf_counter() - t0
        normalized = normalize_metaqa_outputs(questions, predicted_by_qid, kb)
        output_bytes = canonical_json_bytes(normalized)
        return SideResult(
            normalized,
            {
                "wall_time_s": round(elapsed, 6),
                "logical_call_count": calls,
                "upload_bytes": 0,
                "download_bytes": shipped_bytes,
                "output_bytes": output_bytes,
                "transfer_total_bytes": shipped_bytes + output_bytes,
                "transfer_definition": "serialized expanded evidence graph bytes per question + normalized result bytes",
            },
        )

    client = reset_http_metrics(args)
    log_progress(f"[metaqa][script-http] expanding {len(questions)} question(s)")
    for idx, question in enumerate(questions, start=1):
        expanded = http_expand_neighborhood_graph(
            client,
            [question.anchor_entity],
            args.metaqa_hops,
            args.metaqa_direction,
        )
        predicted_by_qid[question.qid] = metaqa_answer_terms_from_graph(
            expanded,
            question.anchor_entity,
            question.answer_relation,
        )
        if idx % 25 == 0 or idx == len(questions):
            log_progress(f"[metaqa][script-http] processed {idx}/{len(questions)} question(s)")
    elapsed = time.perf_counter() - t0
    normalized = normalize_metaqa_outputs(questions, predicted_by_qid, kb)
    return SideResult(
        normalized,
        script_http_metrics(client, normalized, elapsed, "HTTP expanded evidence retrieval bytes per question + normalized result bytes"),
    )


def case_metaqa_anchor_search_rerank_ggf(args: argparse.Namespace) -> SideResult:
    _, questions = load_metaqa_questions(args)
    batches = batched(questions, args.metaqa_anchor_batch_size)
    log_progress(f"[metaqa-anchor][ggf] running {len(batches)} batch(es) of up to {args.metaqa_anchor_batch_size} question(s)")
    rows: list[dict[str, str]] = []
    total_elapsed = 0.0
    total_upload_bytes = 0
    total_http_metrics = HttpMetrics()
    for batch_index, batch in enumerate(batches, start=1):
        query = build_metaqa_anchor_search_rerank_query(args, batch)
        batch_rows, elapsed, http_metrics = run_ggf_query(args, query)
        rows.extend(batch_rows)
        total_elapsed += elapsed
        if http_metrics is None:
            total_upload_bytes += len(query.encode("utf-8"))
        else:
            add_http_metrics(total_http_metrics, http_metrics)
        log_progress(
            f"[metaqa-anchor][ggf] batch {batch_index}/{len(batches)} done in {elapsed:.3f}s with {len(batch_rows)} row(s)"
        )

    ranked_by_qid: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ranked_by_qid.setdefault(row["qid"], []).append(
            {
                "entity": row["entity"],
                "label": row.get("label", ""),
                "rank": int(row["rank"]),
                "originalPosition": int(row.get("originalPosition", row["rank"])),
                "searchScore": float(row.get("searchScore", 0.0)),
                "confidence": float(row.get("confidence", 0.0)),
                "reason": row.get("reason", ""),
            }
        )

    normalized = normalize_metaqa_anchor_rankings(questions, ranked_by_qid, args.anchor_output_top)
    output_bytes = canonical_json_bytes(normalized)
    if args.ggf_access == "http":
        return SideResult(
            normalized_output=normalized,
            metrics=ggf_http_result_metrics(
                total_http_metrics,
                normalized,
                total_elapsed,
                "sum of batched HTTP GGF request/response bytes + compact reranked anchor outputs",
            ),
        )
    return SideResult(
        normalized_output=normalized,
        metrics={
            "wall_time_s": round(total_elapsed, 6),
            "logical_call_count": len(batches),
            "upload_bytes": total_upload_bytes,
            "download_bytes": output_bytes,
            "output_bytes": output_bytes,
            "transfer_total_bytes": total_upload_bytes + output_bytes,
            "transfer_definition": "sum of batched query input bytes + compact reranked anchor outputs",
        },
    )


def case_metaqa_anchor_search_rerank_script(args: argparse.Namespace) -> SideResult:
    _, questions = load_metaqa_questions(args)
    requests_cfg = get_requests_config(args)
    provider = requests_cfg.get("SLM-RERANK-BACKEND", "ollama").strip().lower()
    api_url = requests_cfg.get("SLM-OLLAMA-URL", "http://localhost:11434/api/generate").strip()
    if provider == "groq":
        model = requests_cfg.get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile").strip()
    else:
        model = requests_cfg.get("SLM-OLLAMA-MODEL", "llama3.1:latest").strip()
    timeout = int(requests_cfg.get("SLM-TIMEOUT", 120))

    t0 = time.perf_counter()
    ranked_by_qid: dict[str, list[dict[str, Any]]] = {}
    search_bytes = 0
    rerank_request_bytes = 0
    rerank_response_bytes = 0

    log_progress(f"[metaqa-anchor][script] processing {len(questions)} question(s)")
    for idx, question in enumerate(questions, start=1):
        search_rows = search_anchor_faiss(
            query=question.anchor_label,
            index_dir=args.metaqa_anchor_faiss_dir,
            top_k=args.anchor_search_top_k,
            embedding_model="nomic-embed-text",
        )
        search_bytes += canonical_json_bytes(search_rows)
        ranked_rows, rerank_stats = rerank_candidates_local(
            question_text=question.question_text,
            candidates=search_rows,
            provider=provider,
            api_url=api_url,
            model=model,
            timeout=timeout,
        )
        rerank_request_bytes += int(rerank_stats["request_bytes"])
        rerank_response_bytes += int(rerank_stats["response_bytes"])
        ranked_by_qid[question.qid] = ranked_rows
        if idx % 25 == 0 or idx == len(questions):
            log_progress(f"[metaqa-anchor][script] processed {idx}/{len(questions)} question(s)")

    elapsed = time.perf_counter() - t0
    normalized = normalize_metaqa_anchor_rankings(questions, ranked_by_qid, args.anchor_output_top)
    output_bytes = canonical_json_bytes(normalized)
    client_side_transfer_bytes = search_bytes + rerank_request_bytes + rerank_response_bytes
    return SideResult(
        normalized_output=normalized,
        metrics={
            "wall_time_s": round(elapsed, 6),
            "logical_call_count": len(questions) * 2,
            "upload_bytes": rerank_request_bytes,
            "download_bytes": search_bytes + rerank_response_bytes,
            "output_bytes": output_bytes,
            "transfer_total_bytes": client_side_transfer_bytes,
            "transfer_definition": "client-side FAISS candidate bytes + rerank request/response bytes; no normalized output bytes",
            "sparql_logical_call_count": 0,
            "sparql_upload_bytes": 0,
            "sparql_download_bytes": 0,
            "sparql_transfer_total_bytes": 0,
            "internal_faiss_bytes": search_bytes,
            "internal_rerank_request_bytes": rerank_request_bytes,
            "internal_rerank_response_bytes": rerank_response_bytes,
            "internal_transfer_total_bytes": client_side_transfer_bytes,
        },
    )


CaseRunner = tuple[Callable[[argparse.Namespace], SideResult], Callable[[argparse.Namespace], SideResult], str]


CASE_REGISTRY: dict[str, CaseRunner] = {
    "expand": (case_expand_ggf, case_expand_script, "local_graph"),
    "paths": (case_paths_ggf, case_paths_script, "local_graph"),
    "simrank": (case_simrank_ggf, case_simrank_script, "local_graph"),
    "random_sample": (case_random_sample_ggf, case_random_sample_script, "local_metaqa"),
    "local_schema": (case_local_schema_ggf, case_local_schema_script, "local_metaqa"),
    "metaqa_2hop_local": (case_metaqa_2hop_local_ggf, case_metaqa_2hop_local_script, "local_metaqa"),
    "cbd_esbm_summary": (case_cbd_esbm_ggf, case_cbd_esbm_script, "local_metaqa"),
    "entity_similarity_compare": (case_entity_similarity_ggf, case_entity_similarity_script, "local_metaqa"),
    "entity_similarity_score_only": (case_entity_similarity_score_only_ggf, case_entity_similarity_score_only_script, "local_metaqa"),
    "entity_typing": (case_entity_typing_ggf, case_entity_typing_script, "local_metaqa"),
    "metaqa_anchor_search_rerank_local": (case_metaqa_anchor_search_rerank_ggf, case_metaqa_anchor_search_rerank_script, "local_metaqa"),
}


def ggf_load_paths_for_cases(args: argparse.Namespace, cases: list[str]) -> list[str]:
    paths: list[str] = []
    for case in cases:
        if case == "metaqa_anchor_search_rerank_local":
            continue
        load_path = args.metaqa_kb if case == "metaqa_2hop_local" else args.graph
        resolved = _resolved_path(load_path)
        if resolved and resolved not in paths:
            paths.append(resolved)
    return paths


def run_case(case_name: str, args: argparse.Namespace) -> dict[str, Any]:
    ggf_runner, script_runner, scenario = CASE_REGISTRY[case_name]
    log_verbose(f"{case_name}: running GGF side")
    ggf = ggf_runner(args)
    log_verbose(
        f"{case_name}: GGF done "
        f"(time={ggf.metrics['wall_time_s']:.6f}s, calls={ggf.metrics['logical_call_count']}, "
        f"transfer={ggf.metrics['transfer_total_bytes']}B)"
    )
    log_verbose(f"{case_name}: running script side")
    script = script_runner(args)
    log_verbose(
        f"{case_name}: script done "
        f"(time={script.metrics['wall_time_s']:.6f}s, calls={script.metrics['logical_call_count']}, "
        f"transfer={script.metrics['transfer_total_bytes']}B)"
    )
    equivalent = comparison_view(case_name, ggf.normalized_output) == comparison_view(case_name, script.normalized_output)
    return {
        "case": case_name,
        "scenario": scenario,
        "ggf": {
            "metrics": ggf.metrics,
            "output_hash": canonical_hash(ggf.normalized_output),
            "normalized_output": ggf.normalized_output,
        },
        "script": {
            "metrics": script.metrics,
            "output_hash": canonical_hash(script.normalized_output),
            "normalized_output": script.normalized_output,
        },
        "comparison": {
            "equivalent": equivalent,
        },
    }


def build_summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        ggf_metrics = result["ggf"]["metrics"]
        script_metrics = result["script"]["metrics"]
        ggf_transfer = int(ggf_metrics["transfer_total_bytes"])
        script_transfer = int(script_metrics["transfer_total_bytes"])
        transfer_ratio = None if ggf_transfer == 0 or script_transfer == 0 else round(script_transfer / float(ggf_transfer), 6)
        normalized_output = result["ggf"]["normalized_output"]
        avg_gold_recall = None
        any_gold_match_count = None
        all_gold_matched_count = None
        avg_reciprocal_rank = None
        top1_correct_count = None
        exact_cardinality = None
        estimated_cardinality = None
        cardinality_absolute_error = None
        cardinality_relative_error = None
        if (
            isinstance(normalized_output, list)
            and normalized_output
            and isinstance(normalized_output[0], dict)
            and "gold_recall" in normalized_output[0]
        ):
            recalls = [float(row.get("gold_recall", 0.0)) for row in normalized_output]
            avg_gold_recall = round(sum(recalls) / float(len(recalls)), 6)
            any_gold_match_count = sum(1 for row in normalized_output if row.get("has_any_gold_match"))
            all_gold_matched_count = sum(1 for row in normalized_output if row.get("all_gold_matched"))
        if (
            isinstance(normalized_output, list)
            and normalized_output
            and isinstance(normalized_output[0], dict)
            and "reciprocal_rank" in normalized_output[0]
        ):
            rr_values = [float(row.get("reciprocal_rank", 0.0)) for row in normalized_output]
            avg_reciprocal_rank = round(sum(rr_values) / float(len(rr_values)), 6)
            top1_correct_count = sum(1 for row in normalized_output if row.get("top1_correct"))
        if isinstance(normalized_output, dict) and isinstance(normalized_output.get("metadata"), dict):
            metadata = normalized_output["metadata"]
            if "exactTripleCount" in metadata and "estimatedTripleCount" in metadata:
                exact_cardinality = int(metadata["exactTripleCount"])
                estimated_cardinality = float(metadata["estimatedTripleCount"])
                cardinality_absolute_error = float(metadata.get("absoluteError", abs(estimated_cardinality - exact_cardinality)))
                cardinality_relative_error = float(
                    metadata.get(
                        "relativeError",
                        0.0 if exact_cardinality == 0 else cardinality_absolute_error / float(exact_cardinality),
                    )
                )
        rows.append(
            {
                "case": result["case"],
                "scenario": result["scenario"],
                "equivalent": result["comparison"]["equivalent"],
                "ggf_transfer_total_bytes": ggf_transfer,
                "script_transfer_total_bytes": script_transfer,
                "script_over_ggf_transfer_ratio": transfer_ratio,
                "ggf_logical_call_count": int(ggf_metrics["logical_call_count"]),
                "script_logical_call_count": int(script_metrics["logical_call_count"]),
                "ggf_wall_time_s": float(ggf_metrics["wall_time_s"]),
                "script_wall_time_s": float(script_metrics["wall_time_s"]),
                "ggf_output_hash": result["ggf"]["output_hash"],
                "script_output_hash": result["script"]["output_hash"],
                "avg_gold_recall": avg_gold_recall,
                "questions_with_any_gold_match": any_gold_match_count,
                "questions_with_all_gold_matched": all_gold_matched_count,
                "avg_reciprocal_rank": avg_reciprocal_rank,
                "top1_correct_count": top1_correct_count,
                "exact_cardinality": exact_cardinality,
                "estimated_cardinality": estimated_cardinality,
                "cardinality_absolute_error": cardinality_absolute_error,
                "cardinality_relative_error": cardinality_relative_error,
            }
        )
    return rows


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "case",
                "scenario",
                "equivalent",
                "ggf_transfer_total_bytes",
                "script_transfer_total_bytes",
                "script_over_ggf_transfer_ratio",
                "ggf_logical_call_count",
                "script_logical_call_count",
                "ggf_wall_time_s",
                "script_wall_time_s",
                "ggf_output_hash",
                "script_output_hash",
                "avg_gold_recall",
                "questions_with_any_gold_match",
                "questions_with_all_gold_matched",
                "avg_reciprocal_rank",
                "top1_correct_count",
                "exact_cardinality",
                "estimated_cardinality",
                "cardinality_absolute_error",
                "cardinality_relative_error",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def plot_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    cases = [row["case"] for row in rows]
    x = list(range(len(cases)))
    width = 0.38

    ggf_bytes = [row["ggf_transfer_total_bytes"] for row in rows]
    script_bytes = [row["script_transfer_total_bytes"] for row in rows]
    ggf_calls = [row["ggf_logical_call_count"] for row in rows]
    script_calls = [row["script_logical_call_count"] for row in rows]
    transfer_ratios = [
        float(row["script_over_ggf_transfer_ratio"]) if row["script_over_ggf_transfer_ratio"] is not None else 0.0
        for row in rows
    ]
    ggf_times = [max(float(row["ggf_wall_time_s"]), 1e-6) for row in rows]
    script_times = [max(float(row["script_wall_time_s"]), 1e-6) for row in rows]

    plt.figure(figsize=(max(12, len(cases) * 1.7), 8.2))

    plt.subplot(2, 2, 1)
    plt.bar([i - width / 2 for i in x], ggf_bytes, width=width, label="GGF")
    plt.bar([i + width / 2 for i in x], script_bytes, width=width, label="Script")
    plt.xticks(x, cases, rotation=20, ha="right")
    plt.ylabel("Transferred bytes")
    plt.yscale("log")
    plt.title("Transfer by case (log scale)")
    plt.grid(axis="y", alpha=0.3)
    plt.legend()

    plt.subplot(2, 2, 2)
    plt.bar([i - width / 2 for i in x], ggf_calls, width=width, label="GGF")
    plt.bar([i + width / 2 for i in x], script_calls, width=width, label="Script")
    plt.xticks(x, cases, rotation=20, ha="right")
    plt.ylabel("Logical calls")
    plt.yscale("log")
    plt.title("Calls by case (log scale)")
    plt.grid(axis="y", alpha=0.3)
    plt.legend()

    plt.subplot(2, 2, 3)
    ratio_bars = plt.bar(x, transfer_ratios, width=0.6, color="#d97706")
    plt.xticks(x, cases, rotation=20, ha="right")
    plt.ylabel("Script / GGF transfer ratio")
    plt.yscale("log")
    plt.title("Transfer ratio (log scale)")
    plt.grid(axis="y", alpha=0.3)
    for idx, bar in enumerate(ratio_bars):
        value = transfer_ratios[idx]
        if value <= 0:
            continue
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.1f}x",
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=90,
        )

    plt.subplot(2, 2, 4)
    time_bars_ggf = plt.bar([i - width / 2 for i in x], ggf_times, width=width, label="GGF")
    time_bars_script = plt.bar([i + width / 2 for i in x], script_times, width=width, label="Script")
    plt.xticks(x, cases, rotation=20, ha="right")
    plt.ylabel("Wall time (s)")
    plt.ylim(bottom=0)
    plt.title("Wall time by case")
    plt.grid(axis="y", alpha=0.3)
    plt.legend()
    for bars in (time_bars_ggf, time_bars_script):
        for bar in bars:
            value = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.2f}s",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=90,
            )

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    global VERBOSE
    args = parse_args()
    ConfigSingleton.reset_instance()
    ConfigSingleton(config_file=args.config)
    VERBOSE = bool(args.verbose)
    cases = normalize_cases(args.cases)
    unknown = [case for case in cases if case not in CASE_REGISTRY]
    if unknown:
        raise SystemExit(f"Unknown case(s): {', '.join(unknown)}")
    log_progress(
        f"[runner] starting benchmark with cases={','.join(cases)} "
        f"ggf_access={args.ggf_access} script_access={args.script_access}"
    )
    http_server: LocalSparqlServer | None = None
    ggf_http_server: LocalGgfSparqlServer | None = None
    try:
        if args.ggf_access == "http":
            ggf_load_paths = ggf_load_paths_for_cases(args, cases)
            if len(ggf_load_paths) > 1:
                raise RuntimeError(
                    "GGF HTTP mode currently supports one preloaded RDF graph per benchmark run; "
                    f"requested graphs: {', '.join(ggf_load_paths)}"
                )
            ggf_load_path = ggf_load_paths[0] if ggf_load_paths else ""
            ggf_http_server = LocalGgfSparqlServer(
                repo_root=REPO_ROOT,
                config_path=args.config,
                load_path=ggf_load_path,
                load_format=args.format,
            )
            ggf_http_server.start()
            args._ggf_http_server = ggf_http_server
            args._ggf_http_load_path = ggf_load_path
            args._ggf_http_client = HttpSparqlClient(
                ggf_http_server.endpoint_url,
                simulated_latency_ms=args.http_latency_ms,
            )
            log_progress(
                f"[runner] GGF HTTP SPARQL endpoint ready at {ggf_http_server.endpoint_url} "
                f"(load={ggf_load_path or '<none>'}, latency={args.http_latency_ms:g} ms)"
            )

        if args.script_access == "http":
            http_server = LocalSparqlServer(
                repo_root=REPO_ROOT,
                kb_ttl=args.graph,
                qa_ttl="",
            )
            http_server.start()
            args._http_server = http_server
            args._http_client = HttpSparqlClient(
                http_server.endpoint_url,
                simulated_latency_ms=args.http_latency_ms,
            )
            log_progress(
                f"[runner] HTTP SPARQL endpoint ready at {http_server.endpoint_url} "
                f"(latency={args.http_latency_ms:g} ms)"
            )

        results = []
        for case in cases:
            log_progress(f"[runner] case start: {case}")
            started = time.perf_counter()
            result = run_case(case, args)
            elapsed = time.perf_counter() - started
            results.append(result)
            comparison = result.get("comparison", {})
            status = "equivalent" if comparison.get("equivalent") else "different"
            log_progress(f"[runner] case done: {case} in {elapsed:.3f}s ({status})")

        payload = {
            "cases": cases,
            "results": results,
        }

        summary_rows = build_summary_rows(results)
        payload["summary_rows"] = summary_rows

        out_json = Path(args.out_json)
        out_csv = Path(args.out_csv)
        out_plot = Path(args.out_plot)

        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        write_summary_csv(out_csv, summary_rows)
        plot_summary(out_plot, summary_rows)
        log_progress(f"[runner] wrote JSON: {out_json}")
        log_progress(f"[runner] wrote CSV: {out_csv}")
        log_progress(f"[runner] wrote PNG: {out_plot}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    finally:
        if ggf_http_server is not None:
            ggf_http_server.stop()
            log_progress("[runner] GGF HTTP SPARQL endpoint stopped")
        if http_server is not None:
            http_server.stop()
            log_progress("[runner] HTTP SPARQL endpoint stopped")


if __name__ == "__main__":
    main()
