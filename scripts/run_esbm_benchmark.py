#!/usr/bin/env python3
"""
Run ESBM benchmark baselines and generate consolidated reports.

This runner executes:
1) In-memory simple baselines (random, degree)
2) Orchestrated non-GGF baselines (random, degree)
3) Optional GGF results ingestion (already computed externally)

Outputs:
- consolidated JSON report
- flat CSV summary table for paper-ready comparisons
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ESBM benchmark baselines and aggregate outputs")
    parser.add_argument("--graph", required=True, help="Path to KG file")
    parser.add_argument("--gold", required=True, help="Path to gold summaries (json/jsonl/csv)")
    parser.add_argument("--k", type=int, default=10, help="Summary size")
    parser.add_argument("--neighborhood", choices=["out", "in", "both"], default="out")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baselines", nargs="+", choices=["random", "degree"], default=["random", "degree"])
    parser.add_argument("--out-dir", default="out/esbm-benchmark", help="Output directory")
    parser.add_argument(
        "--ggf-results-json",
        default="",
        help="Optional path to precomputed GGF results JSON to include in consolidated report",
    )
    parser.add_argument(
        "--run-ggf",
        action="store_true",
        help="Run GGF ESBM baseline directly and include it in the consolidated report",
    )
    parser.add_argument(
        "--ggf-modes",
        nargs="+",
        choices=["degree", "random"],
        default=["degree"],
        help="Ranking modes used by the GGF ESBM baseline",
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help="Config file used to register GGFs when --run-ggf is enabled",
    )
    return parser.parse_args()


def _run_cmd(cmd: List[str], cwd: Path) -> Dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_s": round(elapsed, 6),
    }


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_rows(source_name: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    result_block = payload.get("results", {})

    for baseline_name, baseline_payload in result_block.items():
        rows.append(
            {
                "source": source_name,
                "baseline": baseline_payload.get("baseline", baseline_name),
                "k": baseline_payload.get("k", payload.get("config", {}).get("k", "")),
                "n_entities": baseline_payload.get("n_entities", payload.get("config", {}).get("n_entities", "")),
                "micro_precision": baseline_payload.get("micro", {}).get("precision", 0.0),
                "micro_recall": baseline_payload.get("micro", {}).get("recall", 0.0),
                "micro_f1": baseline_payload.get("micro", {}).get("f1", 0.0),
                "macro_precision": baseline_payload.get("macro", {}).get("precision", 0.0),
                "macro_recall": baseline_payload.get("macro", {}).get("recall", 0.0),
                "macro_f1": baseline_payload.get("macro", {}).get("f1", 0.0),
            }
        )
    return rows


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "source",
        "baseline",
        "k",
        "n_entities",
        "micro_precision",
        "micro_recall",
        "micro_f1",
        "macro_precision",
        "macro_recall",
        "macro_f1",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    simple_json = out_dir / "simple_baselines.json"
    orchestrated_json = out_dir / "orchestrated_baselines.json"
    consolidated_json = out_dir / "benchmark_report.json"
    summary_csv = out_dir / "summary.csv"

    simple_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "evaluate_esbm_baselines.py"),
        "--graph",
        args.graph,
        "--gold",
        args.gold,
        "--k",
        str(args.k),
        "--neighborhood",
        args.neighborhood,
        "--seed",
        str(args.seed),
        "--out-json",
        str(simple_json),
        "--baselines",
        *args.baselines,
    ]

    orch_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "evaluate_esbm_orchestrated_baseline.py"),
        "--graph",
        args.graph,
        "--gold",
        args.gold,
        "--k",
        str(args.k),
        "--neighborhood",
        args.neighborhood,
        "--seed",
        str(args.seed),
        "--out-json",
        str(orchestrated_json),
        "--baselines",
        *args.baselines,
    ]

    simple_run = _run_cmd(simple_cmd, ROOT)
    if simple_run["returncode"] != 0:
        print(simple_run["stderr"], file=sys.stderr)
        raise SystemExit("Simple baseline runner failed")

    orch_run = _run_cmd(orch_cmd, ROOT)
    if orch_run["returncode"] != 0:
        print(orch_run["stderr"], file=sys.stderr)
        raise SystemExit("Orchestrated baseline runner failed")

    simple_payload = _load_json(simple_json)
    orch_payload = _load_json(orchestrated_json)

    consolidated: Dict[str, Any] = {
        "config": {
            "graph": args.graph,
            "gold": args.gold,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "seed": args.seed,
            "baselines": args.baselines,
        },
        "runs": {
            "simple": {"elapsed_s": simple_run["elapsed_s"], "out_json": str(simple_json)},
            "orchestrated": {"elapsed_s": orch_run["elapsed_s"], "out_json": str(orchestrated_json)},
        },
        "results": {
            "simple": simple_payload,
            "orchestrated": orch_payload,
        },
    }

    rows = []
    rows.extend(_build_rows("simple", simple_payload))
    rows.extend(_build_rows("orchestrated", orch_payload))

    if args.run_ggf:
        consolidated["runs"]["ggf"] = {}
        consolidated["results"]["ggf"] = {}
        for mode in args.ggf_modes:
            ggf_json = out_dir / f"ggf_baseline_{mode}.json"
            ggf_cmd = [
                sys.executable,
                str(ROOT / "scripts" / "evaluate_esbm_ggf.py"),
                "--graph",
                args.graph,
                "--gold",
                args.gold,
                "--k",
                str(args.k),
                "--neighborhood",
                args.neighborhood,
                "--seed",
                str(args.seed),
                "--mode",
                mode,
                "--config",
                args.config,
                "--out-json",
                str(ggf_json),
            ]

            ggf_run = _run_cmd(ggf_cmd, ROOT)
            if ggf_run["returncode"] != 0:
                print(ggf_run["stderr"], file=sys.stderr)
                raise SystemExit(f"GGF baseline runner failed for mode={mode}")

            ggf_payload = _load_json(ggf_json)
            consolidated["runs"]["ggf"][mode] = {
                "elapsed_s": ggf_run["elapsed_s"],
                "out_json": str(ggf_json),
            }
            consolidated["results"]["ggf"][mode] = ggf_payload
            rows.extend(_build_rows("ggf", ggf_payload))

    if args.ggf_results_json:
        ggf_path = Path(args.ggf_results_json)
        if not ggf_path.exists():
            raise SystemExit(f"GGF results file not found: {ggf_path}")
        ggf_payload = _load_json(ggf_path)
        consolidated["results"]["ggf"] = ggf_payload
        rows.extend(_build_rows("ggf", ggf_payload))

    consolidated_json.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(summary_csv, rows)

    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "report_json": str(consolidated_json),
                "summary_csv": str(summary_csv),
                "sources": [row["source"] for row in rows],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
