#!/usr/bin/env python3
"""Measure transfer scaling (GGF vs script) for entity similarity limits.

Experiment points by default: 10, 20, 30 candidates.
Outputs:
- CSV with per-limit metrics for both methods
- PNG plot (bytes + call counts)
- JSON with full details
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import requests
from rdflib import Graph, URIRef

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import reset_store, store
from SPARQLLM.udf.esbm import select_summary_triples

WD_ENDPOINT = "https://query.wikidata.org/sparql"
WD_JSON_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (similarity transfer scaling)",
}
WD_TTL_HEADERS = {
    "Accept": "text/turtle",
    "User-Agent": "SPARQLLM/0.1 (similarity transfer scaling)",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GGF vs script transfer scaling for entity similarity")
    p.add_argument("--config", default="config.ini")
    p.add_argument("--ref-entity", default="http://www.wikidata.org/entity/Q42")
    p.add_argument("--lang", default="en")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    p.add_argument("--mode", choices=["degree", "random"], default="degree")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limits", nargs="+", type=int, default=[10, 20, 30])
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--out-csv", default="tmp/similarity_transfer_scaling.csv")
    p.add_argument("--out-json", default="tmp/similarity_transfer_scaling.json")
    p.add_argument("--out-plot", default="plots/similarity_transfer_scaling.png")
    return p.parse_args()


def build_ggf_query(ref_entity: str, limit_n: int, lang: str, k: int, neighborhood: str, mode: str, seed: int, top_n: int) -> str:
    return f'''PREFIX wd:       <http://www.wikidata.org/entity/>\nPREFIX wdt:      <http://www.wikidata.org/prop/direct/>\nPREFIX cand:     <http://example.org/cand#>\nPREFIX ggf:      <http://ggf.org/>\n\nSELECT ?entity ?entityLabel ?score ?shared ?differing ?exclusive\nWHERE {{\n  VALUES ?refEntity {{ <{ref_entity}> }}\n\n  {{\n    SELECT ?entity ?entityLabel WHERE {{\n      SERVICE <https://query.wikidata.org/sparql> {{\n        ?entity wdt:P31 wd:Q5 ;\n                wdt:P106 wd:Q36180 ;\n                wdt:P136 wd:Q24925 .\n        FILTER(?entity != <{ref_entity}>)\n      }}\n      BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n    }}\n    ORDER BY ?entityLabel\n    LIMIT {limit_n}\n  }}\n\n  BIND(ggf:CBD(?refEntity, "{lang}") AS ?gRefCBD)\n  BIND(ggf:ESBM-SUMMARY(?gRefCBD, ?refEntity, {k}, "{neighborhood}", "{mode}", {seed}) AS ?gRefSummary)\n\n  BIND(ggf:CBD(?entity, "{lang}") AS ?gEntCBD)\n  BIND(ggf:ESBM-SUMMARY(?gEntCBD, ?entity, {k}, "{neighborhood}", "{mode}", {seed}) AS ?gEntSummary)\n\n  BIND(ggf:COMPARE-GRAPHS(?gRefSummary, ?gEntSummary, ?refEntity, ?entity) AS ?gCmp)\n\n  GRAPH ?gCmp {{\n    ?root a cand:Comparison ;\n          cand:sharedCount ?shared ;\n          cand:differingCount ?differing ;\n          cand:exclusiveCount ?exclusive ;\n          cand:similarityScore ?score .\n  }}\n}}\nORDER BY DESC(?score) DESC(?shared) ?entityLabel\nLIMIT {top_n}\n'''


def build_candidates_query(ref_entity: str, limit_n: int) -> str:
    return f'''PREFIX wd:  <http://www.wikidata.org/entity/>\nPREFIX wdt: <http://www.wikidata.org/prop/direct/>\n\nSELECT ?entity ?entityLabel WHERE {{\n  ?entity wdt:P31 wd:Q5 ;\n          wdt:P106 wd:Q36180 ;\n          wdt:P136 wd:Q24925 .\n  FILTER(?entity != <{ref_entity}>)\n  BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n}}\nORDER BY ?entityLabel\nLIMIT {limit_n}\n'''


def build_cbd_construct_query(entity: str, lang: str) -> str:
    return f'''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX schema: <https://schema.org/>\n\nCONSTRUCT {{\n  <{entity}> ?p ?o .\n  <{entity}> rdfs:label ?lbl .\n  <{entity}> schema:description ?desc .\n  ?bn ?bp ?bo .\n}} WHERE {{\n  <{entity}> ?p ?o .\n  OPTIONAL {{ <{entity}> rdfs:label ?lbl FILTER(lang(?lbl) = "{lang}") }}\n  OPTIONAL {{ <{entity}> schema:description ?desc FILTER(lang(?desc) = "{lang}") }}\n  OPTIONAL {{\n    FILTER(isBlank(?o))\n    BIND(?o AS ?bn)\n    ?bn ?bp ?bo .\n  }}\n}}\n'''


def req_bytes(resp: requests.Response) -> int:
    req = resp.request
    url_b = len((req.url or "").encode("utf-8"))
    body_b = 0
    if req.body:
        body = req.body
        body_b = len(body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8"))
    return url_b + body_b


def rows_csv_bytes(rows: list[dict[str, Any]]) -> int:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["entity", "entityLabel", "score", "shared", "differing", "exclusive"])
    for r in rows:
        w.writerow([r["entity"], r["entityLabel"], r["score"], r["shared"], r["differing"], r["exclusive"]])
    return len(buf.getvalue().encode("utf-8"))


def fetch_candidates(ref_entity: str, limit_n: int) -> tuple[list[dict[str, str]], int, int]:
    q = build_candidates_query(ref_entity, limit_n)
    resp = requests.get(WD_ENDPOINT, params={"query": q}, headers=WD_JSON_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("results", {}).get("bindings", [])
    out = []
    for row in data:
        out.append(
            {
                "entity": row.get("entity", {}).get("value", ""),
                "entityLabel": row.get("entityLabel", {}).get("value", ""),
            }
        )
    return out, req_bytes(resp), len(resp.content or b"")


def fetch_cbd(entity: str, lang: str) -> tuple[Graph, int, int]:
    q = build_cbd_construct_query(entity, lang)
    resp = requests.get(WD_ENDPOINT, params={"query": q}, headers=WD_TTL_HEADERS, timeout=30)
    resp.raise_for_status()
    g = Graph()
    g.parse(data=resp.text, format="turtle")
    return g, req_bytes(resp), len(resp.content or b"")


def summarize_graph(source: Graph, entity: str, k: int, neighborhood: str, mode: str, seed: int) -> Graph:
    out = Graph()
    triples = select_summary_triples(
        source=source,
        entity=entity,
        k=k,
        neighborhood=neighborhood,
        mode=mode,
        seed=seed,
    )
    for t in triples:
        out.add(t)
    return out


def graph_profile(source: Graph, center: str) -> dict[str, set[str]]:
    c = URIRef(center)
    prof: dict[str, set[str]] = {}
    for _, p, o in source.triples((c, None, None)):
        prof.setdefault(str(p), set()).add(f"out|{str(o)}")
    for s, p, _ in source.triples((None, None, c)):
        prof.setdefault(str(p), set()).add(f"in|{str(s)}")
    return prof


def compare_like_udf(g1: Graph, g2: Graph, e1: str, e2: str) -> dict[str, Any]:
    p1 = graph_profile(g1, e1)
    p2 = graph_profile(g2, e2)
    all_props = set(p1) | set(p2)
    shared = 0
    differing = 0
    exclusive = 0
    for p in all_props:
        v1 = p1.get(p, set())
        v2 = p2.get(p, set())
        if v1 and v2:
            shared += 1
            if not (v1 & v2):
                differing += 1
        elif v1 or v2:
            exclusive += 1
    total = shared + exclusive
    score = 0.0 if total == 0 else shared / float(total)
    return {
        "score": round(score, 6),
        "shared": shared,
        "differing": differing,
        "exclusive": exclusive,
    }


def run_ggf(args: argparse.Namespace, limit_n: int) -> dict[str, Any]:
    query = build_ggf_query(
        ref_entity=args.ref_entity,
        limit_n=limit_n,
        lang=args.lang,
        k=args.k,
        neighborhood=args.neighborhood,
        mode=args.mode,
        seed=args.seed,
        top_n=args.top,
    )

    t0 = time.perf_counter()
    qres = store.query(query)
    rows = []
    for r in qres:
        rows.append(
            {
                "entity": str(r[0]),
                "entityLabel": str(r[1]),
                "score": float(r[2]),
                "shared": int(r[3]),
                "differing": int(r[4]),
                "exclusive": int(r[5]),
            }
        )
    elapsed = round(time.perf_counter() - t0, 6)

    upload = len(query.encode("utf-8"))
    download = rows_csv_bytes(rows)

    return {
        "method": "ggf",
        "limit": limit_n,
        "wall_time_s": elapsed,
        "nb_calls": 1,
        "upload_bytes": upload,
        "download_bytes": download,
        "output_bytes": download,
        "transfer_total_bytes": upload + download,
        "rows": rows,
    }


def run_script(args: argparse.Namespace, limit_n: int) -> dict[str, Any]:
    t0 = time.perf_counter()
    calls = 0
    upload = 0
    download = 0

    candidates, up, down = fetch_candidates(args.ref_entity, limit_n)
    calls += 1
    upload += up
    download += down

    # cache reference CBD+summary once
    g_ref_cbd, up, down = fetch_cbd(args.ref_entity, args.lang)
    calls += 1
    upload += up
    download += down
    g_ref_sum = summarize_graph(g_ref_cbd, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed)

    rows = []
    for c in candidates:
        g_ent_cbd, up, down = fetch_cbd(c["entity"], args.lang)
        calls += 1
        upload += up
        download += down

        g_ent_sum = summarize_graph(g_ent_cbd, c["entity"], args.k, args.neighborhood, args.mode, args.seed)
        cmp = compare_like_udf(g_ref_sum, g_ent_sum, args.ref_entity, c["entity"])
        rows.append(
            {
                "entity": c["entity"],
                "entityLabel": c["entityLabel"],
                "score": cmp["score"],
                "shared": cmp["shared"],
                "differing": cmp["differing"],
                "exclusive": cmp["exclusive"],
            }
        )

    rows.sort(key=lambda r: (-float(r["score"]), -int(r["shared"]), str(r["entityLabel"])))
    rows = rows[: args.top]
    elapsed = round(time.perf_counter() - t0, 6)

    out_b = rows_csv_bytes(rows)

    return {
        "method": "script",
        "limit": limit_n,
        "wall_time_s": elapsed,
        "nb_calls": calls,
        "upload_bytes": upload,
        "download_bytes": download,
        "output_bytes": out_b,
        "transfer_total_bytes": upload + download + out_b,
        "rows": rows,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "method",
                "limit",
                "wall_time_s",
                "nb_calls",
                "upload_bytes",
                "download_bytes",
                "output_bytes",
                "transfer_total_bytes",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})


def plot_results(path: Path, rows: list[dict[str, Any]], limits: list[int]) -> None:
    by_method: dict[str, dict[int, dict[str, Any]]] = {"ggf": {}, "script": {}}
    for r in rows:
        by_method[r["method"]][int(r["limit"])] = r

    ggf_bytes = [by_method["ggf"][l]["transfer_total_bytes"] for l in limits]
    script_bytes = [by_method["script"][l]["transfer_total_bytes"] for l in limits]
    ggf_calls = [by_method["ggf"][l]["nb_calls"] for l in limits]
    script_calls = [by_method["script"][l]["nb_calls"] for l in limits]

    plt.figure(figsize=(10, 4.8))

    plt.subplot(1, 2, 1)
    plt.plot(limits, ggf_bytes, marker="o", label="GGF")
    plt.plot(limits, script_bytes, marker="o", label="Script")
    plt.xlabel("Candidate limit")
    plt.ylabel("Client transfer (bytes)")
    plt.title("Data transfer scaling")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(limits, ggf_calls, marker="o", label="GGF")
    plt.plot(limits, script_calls, marker="o", label="Script")
    plt.xlabel("Candidate limit")
    plt.ylabel("HTTP calls")
    plt.title("Call count scaling")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)


def main() -> None:
    args = parse_args()
    limits = [int(x) for x in args.limits]

    # Initialize config once for GGF runs.
    ConfigSingleton.reset_instance()
    ConfigSingleton(config_file=args.config)

    all_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for lim in limits:
        # Use a clean in-memory store per GGF point.
        reset_store()
        ggf = run_ggf(args, lim)
        script = run_script(args, lim)
        all_rows.extend([ggf, script])
        details.append({"limit": lim, "ggf_rows": ggf["rows"], "script_rows": script["rows"]})

    out_csv = Path(args.out_csv)
    out_json = Path(args.out_json)
    out_plot = Path(args.out_plot)

    write_csv(out_csv, all_rows)
    plot_results(out_plot, all_rows, limits)

    payload = {
        "config": {
            "ref_entity": args.ref_entity,
            "lang": args.lang,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
            "limits": limits,
            "top": args.top,
        },
        "summary": all_rows,
        "details": details,
        "artifacts": {
            "csv": str(out_csv),
            "json": str(out_json),
            "plot": str(out_plot),
        },
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"summary": all_rows, "artifacts": payload["artifacts"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
