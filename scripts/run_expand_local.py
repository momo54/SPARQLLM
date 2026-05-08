#!/usr/bin/env python3
"""Run neighborhood expansion outside the SPARQL engine on a local RDF file."""

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

from SPARQLLM.entity_graph_core import expand_neighborhood_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run neighborhood expansion on a local RDF graph")
    parser.add_argument("--graph", default="data/simrank-demo.ttl")
    parser.add_argument("--entity", default="http://ex.org/c")
    parser.add_argument("--hops", type=int, default=1)
    parser.add_argument("--direction", choices=["out", "in", "both"], default="both")
    parser.add_argument("--format", default="turtle")
    parser.add_argument("--out-ttl", default="tmp/expand_local.ttl")
    parser.add_argument("--out-json", default="tmp/expand_local.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = Path(args.graph)

    src = Graph()
    src.parse(source_path, format=args.format)

    started = time.perf_counter()
    expanded = expand_neighborhood_graph(src, [args.entity], args.hops, args.direction)
    elapsed = round(time.perf_counter() - started, 6)

    ttl_data = expanded.serialize(format="turtle")
    out_ttl = Path(args.out_ttl)
    out_json = Path(args.out_json)
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_ttl.write_text(ttl_data, encoding="utf-8")

    result = {
        "config": {
            "graph": str(source_path),
            "entity": args.entity,
            "hops": args.hops,
            "direction": args.direction,
            "format": args.format,
        },
        "metrics": {
            "wall_time_s": elapsed,
            "input_graph_bytes": source_path.stat().st_size,
            "result_output_bytes": len(ttl_data.encode("utf-8")),
            "source_triple_count": len(src),
            "result_triple_count": len(expanded),
        },
    }
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
