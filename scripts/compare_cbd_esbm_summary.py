#!/usr/bin/env python3
"""Compare CBD+ESBM-SUMMARY via GGF query vs client-side script data shipping.

Methodology:
- GGF side: count only query input bytes + final result bytes.
- Script side: count all Wikidata request bytes + response bytes + final result bytes.
- Both sides use the same ESBM summary selection logic from SPARQLLM.udf.esbm.
- The script verifies whether the final triple sets are identical.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

from rdflib import URIRef

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.entity_graph_core import fetch_wikidata_cbd_graph
from SPARQLLM.udf.SPARQLLM import reset_store, store
from SPARQLLM.udf.esbm import select_summary_triples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare CBD+ESBM GGF vs script data shipping")
    parser.add_argument("--entity", default="http://www.wikidata.org/entity/Q42", help="Entity IRI")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    parser.add_argument("--mode", choices=["degree", "random"], default="degree")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", default="config.ini")
    parser.add_argument("--out-json", default="out/cbd_esbm_compare.json")
    parser.add_argument("--out-csv", default="")
    return parser.parse_args()


def build_ggf_query(entity: str, lang: str, k: int, neighborhood: str, mode: str, seed: int) -> str:
    return f'''PREFIX ggf:  <http://ggf.org/>\n\nSELECT ?s ?p ?o\nWHERE {{\n  BIND(ggf:CBD(<{entity}>, "{lang}") AS ?gCBD)\n  BIND(ggf:ESBM-SUMMARY(?gCBD, <{entity}>, {k}, "{neighborhood}", "{mode}", {seed}) AS ?gSummary)\n  GRAPH ?gSummary {{\n    ?s ?p ?o .\n  }}\n}}\n'''
def normalize_triples(triples: list[tuple[Any, Any, Any]]) -> list[tuple[str, str, str]]:
    norm = [(str(s), str(p), str(o)) for s, p, o in triples]
    return sorted(norm)


def csv_bytes_for_triples(triples: list[tuple[str, str, str]]) -> int:
    rows = ["s,p,o\n"]
    for s, p, o in triples:
        rows.append(f'"{s}","{p}","{o}"\n')
    return len("".join(rows).encode("utf-8"))


def write_csv(path: Path, triples: list[tuple[str, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["s", "p", "o"])
        writer.writerows(triples)


def run_ggf_side(args: argparse.Namespace) -> dict[str, Any]:
    ConfigSingleton.reset_instance()
    reset_store()
    ConfigSingleton(config_file=args.config)

    query = build_ggf_query(args.entity, args.lang, args.k, args.neighborhood, args.mode, args.seed)
    started = time.perf_counter()
    qres = store.query(query)
    elapsed = time.perf_counter() - started
    triples = normalize_triples([(row[0], row[1], row[2]) for row in qres])

    return {
        "triples": triples,
        "metrics": {
            "wall_time_s": round(elapsed, 6),
            "query_input_bytes": len(query.encode("utf-8")),
            "result_output_bytes": csv_bytes_for_triples(triples),
            "transfer_total_bytes": len(query.encode("utf-8")) + csv_bytes_for_triples(triples),
            "transfer_definition": "query input bytes + final result bytes",
        },
    }


def run_script_side(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    cbd_graph, upload_bytes, download_bytes = fetch_wikidata_cbd_graph(args.entity, args.lang)
    elapsed = time.perf_counter() - started
    triples = normalize_triples(
        select_summary_triples(
            source=cbd_graph,
            entity=args.entity,
            k=args.k,
            neighborhood=args.neighborhood,
            mode=args.mode,
            seed=args.seed,
        )
    )

    result_bytes = csv_bytes_for_triples(triples)
    return {
        "triples": triples,
        "metrics": {
            "wall_time_s": round(elapsed, 6),
            "wikidata_call_count": 1,
            "wikidata_upload_bytes": upload_bytes,
            "wikidata_download_bytes": download_bytes,
            "result_output_bytes": result_bytes,
            "transfer_total_bytes": upload_bytes + download_bytes + result_bytes,
            "transfer_definition": "all Wikidata request bytes + response bytes + final result bytes",
        },
    }


def main() -> None:
    args = parse_args()
    out_path = Path(args.out_json)

    ggf = run_ggf_side(args)
    script = run_script_side(args)

    triples_equal = ggf["triples"] == script["triples"]

    result = {
        "config": {
            "entity": args.entity,
            "lang": args.lang,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
        },
        "ggf_query": {
            "metrics": ggf["metrics"],
            "triple_count": len(ggf["triples"]),
        },
        "script_data_shipping": {
            "metrics": script["metrics"],
            "triple_count": len(script["triples"]),
        },
        "comparison": {
            "triples_equal": triples_equal,
            "ggf_only_triples": [t for t in ggf["triples"] if t not in script["triples"]],
            "script_only_triples": [t for t in script["triples"] if t not in ggf["triples"]],
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.out_csv:
        write_csv(Path(args.out_csv), ggf["triples"])

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
