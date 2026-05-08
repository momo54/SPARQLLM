#!/usr/bin/env python3
"""Compatibility wrapper for the dedicated xp-ggf-script plotting helper."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "xp-ggf-script" / "plot_metaqa_scaling_summary.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
