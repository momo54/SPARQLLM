#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz


def find_slm_run(explicit: str | None) -> str:
    if explicit:
        return explicit
    venv_bin = Path("./venv/bin/slm-run").resolve()
    if venv_bin.exists():
        return str(venv_bin)
    return "slm-run"  # fallback to PATH


def run_slm(slm_bin: str, config: str, query_file: str, output_csv: str, debug: bool = False) -> None:
    cmd = [slm_bin, "--config", config, "-f", query_file, "-o", output_csv]
    if debug:
        cmd.append("--debug")
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def normalize_city(s: str) -> str:
    return (s or "").strip().lower()


def normalize_text(s: str) -> str:
    # light normalization; we keep punctuation for fuzzy matching robustness
    return (s or "").strip()


def compute_similarity(a: str, b: str) -> dict:
    a = normalize_text(a)
    b = normalize_text(b)
    return {
        "sim_token_set": fuzz.token_set_ratio(a, b),
        "sim_partial": fuzz.partial_ratio(a, b),
        "sim_qratio": fuzz.QRatio(a, b),
        "sim_WRatio": fuzz.WRatio(a, b),
    }


def compare(gen_csv: str, search_csv: str, out_full: str, out_top1: str) -> None:
    gen_df = pd.read_csv(gen_csv)
    search_df = pd.read_csv(search_csv)

    # Expected columns:
    # gen: cityLabel, catLabel, venue, address, capacity, startDate, text
    # search: label, chunk, score, date, name, gf, gl, uri
    # Normalize names for join
    if "cityLabel" not in gen_df.columns:
        raise RuntimeError(f"Missing column 'cityLabel' in {gen_csv}")
    if "label" not in search_df.columns:
        raise RuntimeError(f"Missing column 'label' in {search_csv}")

    gen_df = gen_df.rename(columns={"cityLabel": "city"})
    search_df = search_df.rename(columns={"label": "city"})

    gen_df["city_norm"] = gen_df["city"].map(normalize_city)
    search_df["city_norm"] = search_df["city"].map(normalize_city)

    # Keep only needed columns from generation
    keep_gen = ["city", "city_norm", "startDate", "text", "venue", "address", "capacity"]
    for col in keep_gen:
        if col not in gen_df.columns:
            gen_df[col] = None
    gen_small = gen_df[keep_gen].drop_duplicates(subset=["city_norm"])  # one row per city

    # Merge search results with ground truth per city
    merged = search_df.merge(gen_small, on="city_norm", how="left", suffixes=("_search", "_gen"))

    # Compute similarities and date diffs
    sims = merged.apply(lambda r: compute_similarity(str(r.get("chunk", "")), str(r.get("text", ""))), axis=1, result_type="expand")
    merged = pd.concat([merged, sims], axis=1)

    # Dates
    merged["date_search_dt"] = pd.to_datetime(merged.get("date"), errors="coerce")
    merged["date_gen_dt"] = pd.to_datetime(merged.get("startDate"), errors="coerce")
    merged["date_match"] = (merged["date_search_dt"].notna()) & (merged["date_gen_dt"].notna()) & (merged["date_search_dt"].dt.date == merged["date_gen_dt"].dt.date)
    merged["date_diff_days"] = (merged["date_search_dt"] - merged["date_gen_dt"]).dt.days

    # Rank per city by FAISS score desc
    merged["rank"] = merged.sort_values(["city_norm", "score"], ascending=[True, False]).groupby("city_norm").cumcount() + 1

    # Save full
    Path(out_full).parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_full, index=False)
    print(f"[write] {out_full} ({len(merged)} rows)")

    # Save top-1 per city by score
    top1 = merged.sort_values(["city_norm", "score"], ascending=[True, False]).groupby("city_norm").head(1)
    top1.to_csv(out_top1, index=False)
    print(f"[write] {out_top1} ({len(top1)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Run SPARQLLM generation and FAISS+LLM extraction, then compare results.")
    parser.add_argument("--config", default="config.ini", help="Path to config.ini")
    parser.add_argument("--slm-run", dest="slm_run", default=None, help="Path to slm-run binary (optional)")
    parser.add_argument("--gen-query", default="queries/generate_cultural_event_page.sparql", help="Generation query file")
    parser.add_argument("--search-query", default="queries/city-events-faiss-llm.sparql", help="Search/Extract query file")
    parser.add_argument("--out-dir", default="out", help="Output directory for CSVs")
    parser.add_argument("--skip-generate", action="store_true", help="Skip running generation query")
    parser.add_argument("--skip-search", action="store_true", help="Skip running search/extract query")
    parser.add_argument("--debug", action="store_true", help="Enable debug for slm-run")
    args = parser.parse_args()

    slm_bin = find_slm_run(args.slm_run)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gen_csv = out_dir / "gen.csv"
    search_csv = out_dir / "search.csv"
    out_full = out_dir / "events_compare_full.csv"
    out_top1 = out_dir / "events_compare_top1.csv"

    try:
        if not args.skip_generate:
            run_slm(slm_bin, args.config, args.gen_query, str(gen_csv), debug=args.debug)
        else:
            print("[skip] generation")

        if not args.skip_search:
            run_slm(slm_bin, args.config, args.search_query, str(search_csv), debug=args.debug)
        else:
            print("[skip] search/extract")

        # Ensure inputs exist
        if not gen_csv.exists():
            print(f"[error] Missing {gen_csv}. Rerun without --skip-generate.", file=sys.stderr)
            sys.exit(1)
        if not search_csv.exists():
            print(f"[error] Missing {search_csv}. Rerun without --skip-search.", file=sys.stderr)
            sys.exit(1)

        compare(str(gen_csv), str(search_csv), str(out_full), str(out_top1))
        print("[done] Comparison completed.")
    except subprocess.CalledProcessError as e:
        print(f"[error] slm-run failed: {e}", file=sys.stderr)
        sys.exit(e.returncode or 1)


if __name__ == "__main__":
    main()
