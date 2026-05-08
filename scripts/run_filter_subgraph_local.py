#!/usr/bin/env python3
"""Run FILTER-SUBGRAPH outside the SPARQL engine on a local RDF file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rdflib import Graph

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from SPARQLLM.entity_graph_core import filter_subgraph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FILTER-SUBGRAPH on a local RDF graph")
    parser.add_argument("--graph", default="data/simrank-demo.ttl")
    parser.add_argument("--format", default="turtle")
    parser.add_argument("--predicates", default="")
    parser.add_argument("--nodes", default="")
    parser.add_argument("--node-mode", choices=["touch", "induced"], default="touch")
    parser.add_argument("--keep-literals", action="store_true", default=False)
    parser.add_argument("--out-ttl", default="tmp/filter_subgraph_local.ttl")
    parser.add_argument("--out-json", default="tmp/filter_subgraph_local.json")
    return parser.parse_args()


def parse_csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def main() -> None:
    args = parse_args()
    source_path = Path(args.graph)

    src = Graph()
    src.parse(source_path, format=args.format)

    pred_filter = parse_csv_set(args.predicates)
    node_filter = parse_csv_set(args.nodes)

    started = time.perf_counter()
    filtered = filter_subgraph(src, pred_filter, node_filter, args.node_mode, args.keep_literals)
    elapsed = round(time.perf_counter() - started, 6)

    ttl_data = filtered.serialize(format="turtle")
    out_ttl = Path(args.out_ttl)
    out_json = Path(args.out_json)
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_ttl.write_text(ttl_data, encoding="utf-8")

    result = {
        "config": {
            "graph": str(source_path),
            "format": args.format,
            "predicates": sorted(pred_filter),
            "nodes": sorted(node_filter),
            "node_mode": args.node_mode,
            "keep_literals": args.keep_literals,
        },
        "metrics": {
            "wall_time_s": elapsed,
            "input_graph_bytes": source_path.stat().st_size,
            "result_output_bytes": len(ttl_data.encode("utf-8")),
            "source_triple_count": len(src),
            "result_triple_count": len(filtered),
        },
    }
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
