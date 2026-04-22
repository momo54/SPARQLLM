from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    query_file = repo_root / "queries" / "experimental" / "rml-ggf-demo.sparql"
    config_file = repo_root / "config-rml.ini"

    cmd = [
        sys.executable,
        "-m",
        "SPARQLLM.cli.slm",
        "--config",
        str(config_file),
        "-f",
        str(query_file),
        "--debug",
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")

    print("Running:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(repo_root), env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
