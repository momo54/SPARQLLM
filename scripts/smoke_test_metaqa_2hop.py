#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke-test MetaQA 2-hop files on local KB")
    p.add_argument("--kb", default="data/metaqa/MetaQA/kb.txt")
    p.add_argument("--qa", default="data/metaqa/MetaQA/qa_dev.txt")
    p.add_argument("--limit", type=int, default=20, help="Number of questions to test")
    p.add_argument("--out-json", default="tmp/metaqa_2hop_smoke.json")
    return p.parse_args()


def load_kb(kb_path: Path):
    out_adj = defaultdict(list)
    in_adj = defaultdict(list)
    entities = set()

    for line in kb_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 3:
            continue
        s, p, o = (x.strip() for x in parts)
        out_adj[s].append((p, o))
        in_adj[o].append((p, s))
        entities.add(s)
        entities.add(o)

    return out_adj, in_adj, entities


def load_qa(qa_path: Path):
    rows = []
    for line in qa_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        q, ans = line.split("\t", 1)
        golds = [x.strip() for x in ans.split("|") if x.strip()]
        rows.append((q.strip(), golds))
    return rows


def extract_anchor(question: str) -> str | None:
    m = re.search(r"\[([^\]]+)\]", question)
    if not m:
        return None
    return m.group(1).strip()


def two_hop_neighbors(anchor: str, out_adj, in_adj) -> set[str]:
    hop1 = set()
    for _, nxt in out_adj.get(anchor, []):
        hop1.add(nxt)
    for _, prv in in_adj.get(anchor, []):
        hop1.add(prv)

    hop2 = set()
    for n in hop1:
        for _, nxt in out_adj.get(n, []):
            hop2.add(nxt)
        for _, prv in in_adj.get(n, []):
            hop2.add(prv)

    hop2.discard(anchor)
    return hop2


def main() -> None:
    args = parse_args()
    kb_path = Path(args.kb)
    qa_path = Path(args.qa)

    out_adj, in_adj, entities = load_kb(kb_path)
    qa_rows = load_qa(qa_path)

    tested = 0
    anchors_found = 0
    non_empty_2hop = 0
    hits = 0
    details = []

    for q, golds in qa_rows[: args.limit]:
        tested += 1
        anchor = extract_anchor(q)
        anchor_ok = bool(anchor and anchor in entities)
        if anchor_ok:
            anchors_found += 1

        predicted = set()
        if anchor_ok:
            predicted = two_hop_neighbors(anchor, out_adj, in_adj)
            if predicted:
                non_empty_2hop += 1

        hit = any(g in predicted for g in golds)
        if hit:
            hits += 1

        details.append(
            {
                "question": q,
                "anchor": anchor,
                "anchor_in_kb": anchor_ok,
                "gold_count": len(golds),
                "predicted_2hop_count": len(predicted),
                "hit_any_gold": hit,
            }
        )

    report = {
        "kb": str(kb_path),
        "qa": str(qa_path),
        "tested_questions": tested,
        "anchors_found_in_kb": anchors_found,
        "non_empty_2hop_predictions": non_empty_2hop,
        "hit_any_gold_count": hits,
        "hit_any_gold_rate": 0.0 if tested == 0 else round(hits / tested, 4),
        "details": details,
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "tested_questions": tested,
        "anchors_found_in_kb": anchors_found,
        "non_empty_2hop_predictions": non_empty_2hop,
        "hit_any_gold_count": hits,
        "hit_any_gold_rate": report["hit_any_gold_rate"],
        "out_json": str(out_json),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
