#!/usr/bin/env python3
"""Script baseline for entity similarity (mirrors entity-similarity-compare-ggf.sparql).

Pipeline:
1) Select 10 science-fiction writer candidates from Wikidata (ordered by Q-id string).
2) For each candidate:
   - Fetch CBD(ref)
   - Fetch CBD(candidate)
   - Build ESBM summaries locally
   - Compare summaries with the same property-level logic as COMPARE-GRAPHS
3) Rank and return top results.

Metrics reported:
- nb_calls (Wikidata HTTP calls)
- upload/download bytes
- output bytes
- transfer_total_bytes
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef

from SPARQLLM.entity_graph_core import compare_centered_graphs, fetch_wikidata_cbd_graph, request_bytes
from SPARQLLM.udf.esbm import select_summary_triples

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WD_JSON_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (entity similarity script baseline)",
}
WD_TTL_HEADERS = {
    "Accept": "text/turtle",
    "User-Agent": "SPARQLLM/0.1 (entity similarity script baseline)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Script baseline for entity similarity with transfer metrics")
    parser.add_argument("--ref-entity", default="http://www.wikidata.org/entity/Q42")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    parser.add_argument("--mode", choices=["degree", "random"], default="degree")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--out-json", default="tmp/entity_similarity_compare_script.json")
    parser.add_argument("--out-csv", default="tmp/entity_similarity_compare_script.csv")
    return parser.parse_args()


def build_candidates_query(ref_entity: str, limit_n: int) -> str:
    return f'''PREFIX wd:  <http://www.wikidata.org/entity/>\nPREFIX wdt: <http://www.wikidata.org/prop/direct/>\n\nSELECT ?entity ?entityLabel WHERE {{\n  ?entity wdt:P31 wd:Q5 ;\n          wdt:P106 wd:Q36180 ;\n          wdt:P136 wd:Q24925 .\n  FILTER(?entity != <{ref_entity}>)\n  BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n}}\nORDER BY ?entityLabel\nLIMIT {limit_n}\n'''


def build_cbd_construct_query(entity: str, lang: str) -> str:
    return f'''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX schema: <https://schema.org/>\n\nCONSTRUCT {{\n  <{entity}> ?p ?o .\n  <{entity}> rdfs:label ?lbl .\n  <{entity}> schema:description ?desc .\n  ?bn ?bp ?bo .\n}} WHERE {{\n  <{entity}> ?p ?o .\n  OPTIONAL {{ <{entity}> rdfs:label ?lbl FILTER(lang(?lbl) = "{lang}") }}\n  OPTIONAL {{ <{entity}> schema:description ?desc FILTER(lang(?desc) = "{lang}") }}\n  OPTIONAL {{\n    FILTER(isBlank(?o))\n    BIND(?o AS ?bn)\n    ?bn ?bp ?bo .\n  }}\n}}\n'''

def output_bytes(rows: list[dict[str, Any]]) -> int:
    header = "entity,entityLabel,score,shared,differing,exclusive\n"
    lines = [header]
    for r in rows:
        lines.append(
            f'"{r["entity"]}","{r["entityLabel"]}",{r["score"]},{r["shared"]},{r["differing"]},{r["exclusive"]}\n'
        )
    return len("".join(lines).encode("utf-8"))

def fetch_candidates(ref_entity: str, limit_n: int) -> tuple[list[dict[str, str]], int, int]:
    q = build_candidates_query(ref_entity, limit_n)
    import requests

    resp = requests.get(
        WIKIDATA_SPARQL_ENDPOINT,
        params={"query": q},
        headers=WD_JSON_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json().get("results", {}).get("bindings", [])
    out = []
    for r in rows:
        out.append(
            {
                "entity": r.get("entity", {}).get("value", ""),
                "entityLabel": r.get("entityLabel", {}).get("value", ""),
            }
        )
    return out, request_bytes(resp), len(resp.content or b"")


def fetch_cbd(entity: str, lang: str) -> tuple[Graph, int, int]:
    return fetch_wikidata_cbd_graph(entity, lang)


def summarize(graph: Graph, entity: str, k: int, neighborhood: str, mode: str, seed: int) -> Graph:
    triples = select_summary_triples(
        source=graph,
        entity=entity,
        k=k,
        neighborhood=neighborhood,
        mode=mode,
        seed=seed,
    )
    out = Graph()
    for t in triples:
        out.add(t)
    return out


def main() -> None:
    args = parse_args()
    t0 = time.perf_counter()

    total_calls = 0
    up_bytes = 0
    down_bytes = 0

    candidates, up, down = fetch_candidates(args.ref_entity, args.candidate_limit)
    total_calls += 1
    up_bytes += up
    down_bytes += down

    rows: list[dict[str, Any]] = []
    for c in candidates:
        g_ref, up1, down1 = fetch_cbd(args.ref_entity, args.lang)
        total_calls += 1
        up_bytes += up1
        down_bytes += down1

        g_ent, up2, down2 = fetch_cbd(c["entity"], args.lang)
        total_calls += 1
        up_bytes += up2
        down_bytes += down2

        g_ref_sum = summarize(g_ref, args.ref_entity, args.k, args.neighborhood, args.mode, args.seed)
        g_ent_sum = summarize(g_ent, c["entity"], args.k, args.neighborhood, args.mode, args.seed)

        cmp = compare_centered_graphs(g_ref_sum, g_ent_sum, args.ref_entity, c["entity"])
        rows.append(
            {
                "entity": c["entity"],
                "entityLabel": c["entityLabel"],
                "score": cmp.similarity_score,
                "shared": cmp.shared_count,
                "differing": cmp.differing_count,
                "exclusive": cmp.exclusive_count,
            }
        )

    rows.sort(key=lambda r: (-float(r["score"]), -int(r["shared"]), str(r["entityLabel"])))
    top_rows = rows[: args.top]

    out_b = output_bytes(top_rows)
    elapsed = round(time.perf_counter() - t0, 6)

    result = {
        "config": {
            "ref_entity": args.ref_entity,
            "lang": args.lang,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
            "candidate_limit": args.candidate_limit,
            "top": args.top,
        },
        "metrics": {
            "wall_time_s": elapsed,
            "nb_calls": total_calls,
            "upload_bytes": up_bytes,
            "download_bytes": down_bytes,
            "output_bytes": out_b,
            "transfer_total_bytes": up_bytes + down_bytes + out_b,
            "transfer_definition": "all Wikidata request bytes + response bytes + final output bytes",
        },
        "intermediate": {
            "candidate_count": len(candidates),
            "comparisons_executed": len(rows),
            "expected_calls_formula": "1 + 2 * comparisons_executed",
            "expected_calls_value": 1 + 2 * len(rows),
        },
        "top_results": top_rows,
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.out_csv:
        out_csv = Path(args.out_csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["entity", "entityLabel", "score", "shared", "differing", "exclusive"])
            w.writeheader()
            w.writerows(top_rows)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
