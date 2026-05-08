#!/usr/bin/env python3
"""Plot a compact MetaQA scaling summary from benchmark JSON outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
BENCH_TMP_DIR = BENCH_ROOT / "tmp"
BENCH_OUT_DIR = BENCH_ROOT / "out"

BENCH_TMP_DIR.mkdir(parents=True, exist_ok=True)
BENCH_OUT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(BENCH_TMP_DIR / "mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(BENCH_TMP_DIR / "cache"))

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot a compact MetaQA scaling summary.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=[
            str(BENCH_OUT_DIR / "metaqa_20.json"),
            str(BENCH_OUT_DIR / "metaqa_50.json"),
            str(BENCH_OUT_DIR / "metaqa_100_optimized.json"),
        ],
        help="Benchmark JSON files produced by xp-ggf-script/evaluate_ggf_vs_script.py",
    )
    parser.add_argument("--out", default=str(BENCH_OUT_DIR / "metaqa_scaling_summary.png"))
    return parser.parse_args()


def load_summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload["summary_rows"][0]
    normalized = payload["results"][0]["ggf"]["normalized_output"]
    return {
        "label": str(len(normalized)),
        "usable_questions": len(normalized),
        "ggf_time_s": float(summary["ggf_wall_time_s"]),
        "script_time_s": float(summary["script_wall_time_s"]),
        "ggf_bytes_mb": float(summary["ggf_transfer_total_bytes"]) / (1024.0 * 1024.0),
        "script_bytes_mb": float(summary["script_transfer_total_bytes"]) / (1024.0 * 1024.0),
        "avg_gold_recall": float(summary["avg_gold_recall"]),
    }


def main() -> None:
    args = parse_args()
    rows = [load_summary(Path(path)) for path in args.inputs]
    rows.sort(key=lambda row: row["usable_questions"])

    x_labels = [row["label"] for row in rows]
    x = list(range(len(rows)))

    ggf_times = [row["ggf_time_s"] for row in rows]
    script_times = [row["script_time_s"] for row in rows]
    ggf_bytes = [row["ggf_bytes_mb"] for row in rows]
    script_bytes = [row["script_bytes_mb"] for row in rows]
    recalls = [row["avg_gold_recall"] for row in rows]

    plt.figure(figsize=(9, 4.8))

    plt.subplot(1, 2, 1)
    plt.plot(x, ggf_times, marker="o", linewidth=2, label="GGF")
    plt.plot(x, script_times, marker="o", linewidth=2, label="Script")
    plt.xticks(x, x_labels)
    plt.xlabel("Usable questions")
    plt.ylabel("Wall time (s)")
    plt.title("Execution time")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(x, ggf_bytes, marker="o", linewidth=2, label="GGF")
    plt.plot(x, script_bytes, marker="o", linewidth=2, label="Script")
    for idx, recall in enumerate(recalls):
        plt.annotate(f"R={recall:.3f}", (x[idx], script_bytes[idx]), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)
    plt.xticks(x, x_labels)
    plt.xlabel("Usable questions")
    plt.ylabel("Transferred data (MB)")
    plt.title("Transfer volume")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.suptitle("MetaQA scaling summary", fontsize=12)
    plt.tight_layout()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(out_path)


if __name__ == "__main__":
    main()
