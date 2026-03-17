#!/usr/bin/env python3
"""Compare a LangChain StructGPT-like orchestration against a GGF-supported query."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run_langchain(question: str, provider: str, model: str, config: str, env_file: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="structgpt_langchain_") as tmpdir:
        out_path = Path(tmpdir) / "langchain.json"
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "langchain_structgpt_like.py"),
            "--question",
            question,
            "--provider",
            provider,
            "--config",
            config,
            "--env-file",
            env_file,
            "--out",
            str(out_path),
        ]
        if model:
            cmd.extend(["--model", model])

        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        if proc.returncode != 0:
            raise RuntimeError(f"LangChain pipeline failed: {proc.stderr.strip()}")

        with open(out_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    return {
        "wall_time_s": round(elapsed, 3),
        "answer": data.get("answer", ""),
        "anchor_label": data.get("anchor_label", ""),
        "anchor_qid": data.get("anchor_qid", ""),
        "candidate_count": len(data.get("candidates", [])),
        "top_candidates": [item.get("label", "") for item in data.get("candidates", [])[:5]],
        "metrics": data.get("metrics", {}),
    }


def _run_ggf(config: str, query_file: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="structgpt_ggf_") as tmpdir:
        csv_path = Path(tmpdir) / "ggf.csv"
        metrics_path = Path(tmpdir) / "ggf_metrics.json"
        cmd = [
            sys.executable,
            "-m",
            "SPARQLLM.cli.slm",
            "--config",
            config,
            "-f",
            query_file,
            "--metrics-out",
            str(metrics_path),
            "-o",
            str(csv_path),
        ]

        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        elapsed = time.perf_counter() - started
        if proc.returncode != 0:
            raise RuntimeError(f"GGF pipeline failed: {proc.stderr.strip()}")

        with open(metrics_path, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)

        with open(csv_path, "r", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    answer = rows[0].get("answer", "") if rows else ""
    total_wd_calls = rows[0].get("totalWdCalls", "") if rows else ""
    top_candidates = [row.get("label", "") for row in rows[:5]]
    return {
        "wall_time_s": round(elapsed, 3),
        "answer": answer,
        "candidate_count": len(rows),
        "top_candidates": top_candidates,
        "metrics": metrics,
        "wikidata_call_count": total_wd_calls,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare LangChain StructGPT-like vs GGF StructGPT-like.")
    parser.add_argument("--question", default="I am looking for science-fiction authors similar to Isaac Asimov")
    parser.add_argument("--provider", choices=["groq", "ollama"], default="groq")
    parser.add_argument("--model", default="")
    parser.add_argument("--config", default=str(ROOT / "config.ini"))
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--ggf-query", default=str(ROOT / "queries" / "entitysearch" / "structgpt-ggf-demo.sparql"))
    parser.add_argument("--out", default="")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    langchain = _run_langchain(args.question, args.provider, args.model, args.config, args.env_file)
    ggf = _run_ggf(args.config, args.ggf_query)

    comparison = {
        "question": args.question,
        "langchain_structgpt": langchain,
        "ggf_structgpt": ggf,
    }

    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(comparison, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))