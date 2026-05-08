#!/usr/bin/env python3
"""Wikidata entity similarity pipeline using SPARQL candidates + DESCRIBE-like CBD fetches.

Pipeline:
1. Select a candidate pool with a SPARQL query.
2. Fetch a CBD-like graph for the reference entity.
3. Summarize the reference graph locally.
4. For each candidate:
   - fetch its CBD-like graph
   - summarize it locally
   - compare the two summaries
5. Rank by similarity and keep the top-k.

The JSON output intentionally keeps both intermediate and final artifacts:
- candidate list
- reference CBD and summary
- per-candidate CBD stats, summaries, and comparison scores
- final top-k ranking
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from rdflib import Graph

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SPARQLLM.entity_graph_core import (
    WIKIDATA_SPARQL_ENDPOINT,
    compare_centered_graphs,
    fetch_wikidata_cbd_graph,
    normalize_wikidata_entity_iri,
    request_bytes,
)
from SPARQLLM.udf.esbm import select_summary_triples

WD_JSON_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (wikidata similarity describe script)",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Wikidata entity similarity with SPARQL candidates and DESCRIBE-like fetches")
    p.add_argument("--ref-entity", required=True, help="Reference Wikidata entity IRI or Q-id")
    p.add_argument("--lang", default="en")
    p.add_argument("--candidate-limit", type=int, default=20)
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    p.add_argument("--mode", choices=["degree", "random"], default="degree")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--film-class", default="Q11424", help="Film class used in the candidate query")
    p.add_argument("--genre", default="Q24925", help="Genre entity used in the candidate query")
    p.add_argument(
        "--out-json",
        default="tmp/wikidata_entity_similarity_describe.json",
        help="Detailed JSON output with intermediates and final ranking",
    )
    p.add_argument(
        "--out-csv",
        default="tmp/wikidata_entity_similarity_describe.csv",
        help="CSV output for the final top-k ranking",
    )
    p.add_argument(
        "--include-summary-triples",
        action="store_true",
        help="Include summary triples for the reference and candidates in the JSON output",
    )
    return p.parse_args()


def build_candidate_query(ref_entity: str, film_class: str, genre_entity: str, limit_n: int, lang: str) -> str:
    return f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT ?entity ?entityLabel WHERE {{
  ?entity wdt:P31/wdt:P279* <{film_class}> ;
          wdt:P136 <{genre_entity}> .
  FILTER(?entity != <{ref_entity}>)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }}
}}
ORDER BY ?entityLabel
LIMIT {limit_n}
"""


def fetch_candidates(ref_entity: str, film_class: str, genre_entity: str, limit_n: int, lang: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    query = build_candidate_query(ref_entity, film_class, genre_entity, limit_n, lang)
    resp = requests.get(
        WIKIDATA_SPARQL_ENDPOINT,
        params={"query": query},
        headers=WD_JSON_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    rows = [
        {
            "entity": row.get("entity", {}).get("value", ""),
            "entityLabel": row.get("entityLabel", {}).get("value", ""),
        }
        for row in bindings
    ]
    metrics = {
        "query": query,
        "call_count": 1,
        "upload_bytes": request_bytes(resp),
        "download_bytes": len(resp.content or b""),
        "candidate_count": len(rows),
    }
    return rows, metrics


def summarize(graph: Graph, entity: str, k: int, neighborhood: str, mode: str, seed: int) -> tuple[Graph, list[list[str]]]:
    triples = select_summary_triples(
        source=graph,
        entity=entity,
        k=k,
        neighborhood=neighborhood,
        mode=mode,
        seed=seed,
    )
    out = Graph()
    normalized: list[list[str]] = []
    for s, p, o in triples:
        out.add((s, p, o))
        normalized.append([str(s), str(p), str(o)])
    normalized.sort()
    return out, normalized


def main() -> None:
    args = parse_args()
    t0 = time.perf_counter()

    ref_entity = normalize_wikidata_entity_iri(args.ref_entity)
    film_class = normalize_wikidata_entity_iri(args.film_class)
    genre_entity = normalize_wikidata_entity_iri(args.genre)

    total_calls = 0
    upload_bytes = 0
    download_bytes = 0

    candidates, candidate_metrics = fetch_candidates(ref_entity, film_class, genre_entity, args.candidate_limit, args.lang)
    total_calls += candidate_metrics["call_count"]
    upload_bytes += candidate_metrics["upload_bytes"]
    download_bytes += candidate_metrics["download_bytes"]

    ref_graph, up_ref, down_ref = fetch_wikidata_cbd_graph(ref_entity, args.lang)
    total_calls += 1
    upload_bytes += up_ref
    download_bytes += down_ref
    ref_summary_graph, ref_summary_triples = summarize(ref_graph, ref_entity, args.k, args.neighborhood, args.mode, args.seed)

    comparisons: list[dict[str, Any]] = []
    for candidate in candidates:
        cand_graph, up_c, down_c = fetch_wikidata_cbd_graph(candidate["entity"], args.lang)
        total_calls += 1
        upload_bytes += up_c
        download_bytes += down_c

        cand_summary_graph, cand_summary_triples = summarize(
            cand_graph,
            candidate["entity"],
            args.k,
            args.neighborhood,
            args.mode,
            args.seed,
        )
        cmp = compare_centered_graphs(ref_summary_graph, cand_summary_graph, ref_entity, candidate["entity"])

        row = {
            "entity": candidate["entity"],
            "entityLabel": candidate["entityLabel"],
            "cbd_triple_count": len(cand_graph),
            "summary_triple_count": len(cand_summary_graph),
            "score": cmp.similarity_score,
            "shared": cmp.shared_count,
            "differing": cmp.differing_count,
            "exclusive": cmp.exclusive_count,
        }
        if args.include_summary_triples:
            row["summary_triples"] = cand_summary_triples
        comparisons.append(row)

    comparisons.sort(key=lambda row: (-float(row["score"]), -int(row["shared"]), str(row["entityLabel"])))
    top_results = comparisons[: args.top]

    output_payload = {
        "config": {
            "ref_entity": ref_entity,
            "lang": args.lang,
            "candidate_limit": args.candidate_limit,
            "top": args.top,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
            "film_class": film_class,
            "genre": genre_entity,
        },
        "metrics": {
            "wall_time_s": round(time.perf_counter() - t0, 6),
            "call_count": total_calls,
            "upload_bytes": upload_bytes,
            "download_bytes": download_bytes,
            "transfer_total_bytes": upload_bytes + download_bytes,
            "transfer_definition": "candidate SPARQL query bytes + all DESCRIBE-like CBD request/response bytes",
        },
        "intermediate": {
            "candidates": candidates,
            "reference": {
                "entity": ref_entity,
                "cbd_triple_count": len(ref_graph),
                "summary_triple_count": len(ref_summary_graph),
                **({"summary_triples": ref_summary_triples} if args.include_summary_triples else {}),
            },
            "comparisons": comparisons,
        },
        "final": {
            "top_results": top_results,
        },
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    csv_fields = ["entity", "entityLabel", "score", "shared", "differing", "exclusive", "cbd_triple_count", "summary_triple_count"]
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=csv_fields,
        )
        writer.writeheader()
        writer.writerows([{field: row.get(field) for field in csv_fields} for row in top_results])

    print(json.dumps(output_payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
