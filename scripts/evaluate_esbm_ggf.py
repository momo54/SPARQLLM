#!/usr/bin/env python3
"""
Evaluate ESBM summaries produced by the ESBM-SUMMARY GGF.

This script computes the same triple-level micro/macro P/R/F1 as the Python
baselines, but summaries are generated in-query via:
  BIND(ggf:ESBM-SUMMARY(...) AS ?gSummary)
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from rdflib import Graph, URIRef

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import reset_store, store

Triple = Tuple[str, str, str]
GoldMap = Dict[str, Set[Triple]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ESBM GGF baseline")
    parser.add_argument("--graph", required=True, help="Path to KG file")
    parser.add_argument("--gold", required=True, help="Path to gold summaries (json/jsonl/csv)")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--neighborhood", choices=["out", "in", "both"], default="out")
    parser.add_argument("--mode", choices=["degree", "random"], default="degree")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", default="config.ini", help="Config with GGF associations")
    parser.add_argument("--out-json", default="out/esbm_ggf_results.json")
    return parser.parse_args()


def guess_format(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".ttl":
        return "turtle"
    if ext == ".nt":
        return "nt"
    if ext == ".nq":
        return "nquads"
    if ext == ".trig":
        return "trig"
    if ext in {".rdf", ".xml"}:
        return "xml"
    if ext == ".jsonld":
        return "json-ld"
    return None


def parse_gold(path: Path) -> GoldMap:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_gold_json(path)
    if suffix == ".jsonl":
        return _parse_gold_jsonl(path)
    if suffix == ".csv":
        return _parse_gold_csv(path)
    raise ValueError(f"Unsupported gold format: {path}")


def _normalize_triple(raw: Sequence[str]) -> Triple:
    if len(raw) != 3:
        raise ValueError(f"Expected triple of len 3, got: {raw}")
    s, p, o = raw
    return str(s), str(p), str(o)


def _parse_gold_json(path: Path) -> GoldMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: GoldMap = {}
    for entity, triples in data.items():
        out[str(entity)] = {_normalize_triple(t) for t in triples}
    return out


def _parse_gold_jsonl(path: Path) -> GoldMap:
    out: GoldMap = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            entity = str(row["entity"])
            triples = {_normalize_triple(t) for t in row["triples"]}
            if entity in out:
                out[entity].update(triples)
            else:
                out[entity] = triples
    return out


def _parse_gold_csv(path: Path) -> GoldMap:
    out: GoldMap = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"entity", "s", "p", "o"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV gold file missing required columns: {sorted(missing)}")
        for row in reader:
            entity = str(row["entity"])
            triple: Triple = (str(row["s"]), str(row["p"]), str(row["o"]))
            if entity in out:
                out[entity].add(triple)
            else:
                out[entity] = {triple}
    return out


def is_iri(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def compute_prf(pred: Iterable[Triple], gold: Set[Triple]) -> Dict[str, float]:
    pred_set = set(pred)
    tp = len(pred_set & gold)
    fp = len(pred_set - gold)
    fn = len(gold - pred_set)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def load_source_into_store(graph_path: Path) -> URIRef:
    source_uri = URIRef("urn:esbm:source")
    src_ctx = store.get_context(source_uri)
    src_ctx.remove((None, None, None))

    g = Graph()
    g.parse(graph_path, format=guess_format(graph_path))
    for t in g:
        src_ctx.add(t)
    return source_uri


def run_ggf_summary(source_uri: URIRef, entity: str, k: int, neighborhood: str, mode: str, seed: int) -> List[Triple]:
    query = f"""
PREFIX ggf: <http://ggf.org/>
SELECT ?s ?p ?o
WHERE {{
  BIND(ggf:ESBM-SUMMARY(<{source_uri}>, <{entity}>, {k}, \"{neighborhood}\", \"{mode}\", {seed}) AS ?gSummary)
  GRAPH ?gSummary {{
    ?s ?p ?o .
  }}
}}
"""

    qres = store.query(query)
    triples: List[Triple] = []
    for row in qres:
        triples.append((str(row[0]), str(row[1]), str(row[2])))
    return triples


def main() -> None:
    args = parse_args()

    ConfigSingleton.reset_instance()
    reset_store()
    ConfigSingleton(config_file=args.config)

    graph_path = Path(args.graph)
    gold_path = Path(args.gold)
    out_path = Path(args.out_json)

    gold_map = parse_gold(gold_path)
    entities_all = sorted(gold_map.keys())
    entities = [e for e in entities_all if is_iri(e)]
    skipped = [e for e in entities_all if not is_iri(e)]

    source_uri = load_source_into_store(graph_path)

    per_entity = {}
    sum_tp = sum_fp = sum_fn = 0

    for entity in entities:
        pred = run_ggf_summary(source_uri, entity, args.k, args.neighborhood, args.mode, args.seed)
        m = compute_prf(pred, gold_map[entity])
        per_entity[entity] = m
        sum_tp += m["tp"]
        sum_fp += m["fp"]
        sum_fn += m["fn"]

    micro_p = sum_tp / (sum_tp + sum_fp) if (sum_tp + sum_fp) else 0.0
    micro_r = sum_tp / (sum_tp + sum_fn) if (sum_tp + sum_fn) else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    macro_p = sum(v["precision"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0
    macro_r = sum(v["recall"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0
    macro_f1 = sum(v["f1"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0

    results = {
        "config": {
            "graph": str(graph_path),
            "gold": str(gold_path),
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
            "n_entities_total": len(entities_all),
            "n_entities_evaluated": len(entities),
            "n_entities_skipped": len(skipped),
        },
        "results": {
            args.mode: {
                "baseline": f"ggf_{args.mode}",
                "k": args.k,
                "n_entities": len(entities),
                "micro": {
                    "precision": micro_p,
                    "recall": micro_r,
                    "f1": micro_f1,
                    "tp": sum_tp,
                    "fp": sum_fp,
                    "fn": sum_fn,
                },
                "macro": {
                    "precision": macro_p,
                    "recall": macro_r,
                    "f1": macro_f1,
                },
                "per_entity": per_entity,
            }
        },
        "skipped_entities": skipped,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_path),
                "baseline": f"ggf_{args.mode}",
                "micro_f1": micro_f1,
                "macro_f1": macro_f1,
                "n_entities_evaluated": len(entities),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
