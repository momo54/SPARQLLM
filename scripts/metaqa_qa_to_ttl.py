#!/usr/bin/env python3
"""Convert a MetaQA qa_dev.txt file to a Turtle knowledge graph of questions.

Each question becomes a mqqa:Question resource with:
  - mqqa:id         : unique string identifier
  - mqqa:text       : verbatim question text (preserves [Anchor] brackets)
  - mqqa:goldAnswer : one value per tab-separated answer (multi-valued)

Usage
-----
venv/bin/python scripts/metaqa_qa_to_ttl.py \\
    --qa  data/metaqa/MetaQA/qa_dev.txt \\
    --out data/metaqa/MetaQA/qa_2hop.ttl

The output can then be passed alongside kb.ttl to the eval query.
"""

import argparse
import re
import sys
from pathlib import Path


def escape_ttl_string(s: str) -> str:
    """Escape special characters for a Turtle string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def convert(qa_file: str, out_file: str, limit: int) -> None:
    lines = Path(qa_file).read_text(encoding="utf-8").splitlines()

    triples: list[str] = [
        "@prefix mqqa: <http://metaqa.org/qa#> .",
        "@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]

    count = 0
    for i, raw_line in enumerate(lines):
        if limit > 0 and count >= limit:
            break

        parts = raw_line.strip().split("\t")
        if len(parts) < 2:
            continue

        question = parts[0].strip()
        answers = [a.strip() for a in parts[1].split("|") if a.strip()]

        # Must have an [Anchor] entity and at least one answer
        if not answers or not re.search(r"\[.+\]", question):
            continue

        qid = f"q{i + 1}"
        q_escaped = escape_ttl_string(question)

        triples.append(f"<urn:metaqa:question/{qid}>")
        triples.append(f"    a mqqa:Question ;")
        triples.append(f'    mqqa:id "{qid}" ;')
        triples.append(f'    mqqa:text "{q_escaped}" ;')

        for j, ans in enumerate(answers):
            ans_escaped = escape_ttl_string(ans)
            sep = ";" if j < len(answers) - 1 else "."
            triples.append(f'    mqqa:goldAnswer "{ans_escaped}" {sep}')

        triples.append("")
        count += 1

    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    Path(out_file).write_text("\n".join(triples), encoding="utf-8")
    print(f"Wrote {count} questions to {out_file}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert MetaQA QA file to Turtle KG.")
    parser.add_argument("--qa",    required=True, help="Path to qa_dev.txt (tab-separated)")
    parser.add_argument("--out",   required=True, help="Output TTL file path")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max questions to convert (0 = all questions, default: all)",
    )
    args = parser.parse_args()

    convert(args.qa, args.out, args.limit)
