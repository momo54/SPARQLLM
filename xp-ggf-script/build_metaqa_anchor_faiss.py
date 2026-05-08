#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from SPARQLLM.metaqa_anchor_faiss import build_anchor_faiss_index


def default_metaqa_kb_path() -> str:
    return "data/metaqa/MetaQA/kb.ttl"


def default_metaqa_qa_path() -> str:
    return "data/metaqa/MetaQA/qa_2hop.ttl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a persistent FAISS index over MetaQA anchor entities.")
    parser.add_argument("--kb", default=default_metaqa_kb_path(), help="Path to MetaQA kb.ttl")
    parser.add_argument("--qa", default=default_metaqa_qa_path(), help="Path to MetaQA qa_2hop.ttl")
    parser.add_argument(
        "--out-dir",
        default="xp-ggf-script/data/metaqa_anchor_faiss",
        help="Directory where FAISS index, mapping, manifest, and documents will be stored",
    )
    parser.add_argument("--embedding-model", default="nomic-embed-text", help="Local Ollama embedding model")
    parser.add_argument(
        "--embeddings-url",
        default="http://localhost:11434/api/embeddings",
        help="Local embeddings endpoint",
    )
    parser.add_argument(
        "--limit-questions",
        type=int,
        default=0,
        help="Optional cap on the number of MetaQA questions used to derive the anchor pool (0 = all)",
    )
    parser.add_argument(
        "--max-triples",
        type=int,
        default=25,
        help="Maximum number of CBD triples rendered into each entity document",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    manifest = build_anchor_faiss_index(
        kb_path=args.kb,
        qa_path=args.qa,
        out_dir=args.out_dir,
        embedding_model=args.embedding_model,
        embeddings_url=args.embeddings_url,
        limit_questions=args.limit_questions,
        max_triples=args.max_triples,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
