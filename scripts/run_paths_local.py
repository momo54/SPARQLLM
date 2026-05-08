#!/usr/bin/env python3
"""Run PATHS outside the SPARQL engine on a local RDF file."""

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

from SPARQLLM.entity_graph_core import shortest_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run shortest PATHS on a local RDF graph")
    parser.add_argument("--graph", default="data/simrank-demo.ttl")
    parser.add_argument("--format", default="turtle")
    parser.add_argument("--start", default="http://ex.org/a")
    parser.add_argument("--goal", default="http://ex.org/g")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--direction", choices=["out", "in", "both"], default="out")
    parser.add_argument("--max-paths", type=int, default=10)
    parser.add_argument("--out-json", default="tmp/paths_local.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = Path(args.graph)

    src = Graph()
    src.parse(source_path, format=args.format)

    started = time.perf_counter()
    paths = shortest_paths(src, args.start, args.goal, args.max_depth, args.direction, args.max_paths)
    elapsed = round(time.perf_counter() - started, 6)

    serializable = [
        [{"src": str(s), "pred": str(p), "dst": str(o)} for (s, p, o) in path]
        for path in paths
    ]

    result = {
        "config": {
            "graph": str(source_path),
            "format": args.format,
            "start": args.start,
            "goal": args.goal,
            "max_depth": args.max_depth,
            "direction": args.direction,
            "max_paths": args.max_paths,
        },
        "metrics": {
            "wall_time_s": elapsed,
            "input_graph_bytes": source_path.stat().st_size,
            "source_triple_count": len(src),
            "path_count": len(paths),
        },
        "paths": serializable,
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
