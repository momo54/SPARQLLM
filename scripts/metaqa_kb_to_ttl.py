#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert MetaQA kb.txt (pipe format) to Turtle")
    p.add_argument("--kb", default="data/metaqa/MetaQA/kb.txt")
    p.add_argument("--out", default="data/metaqa/MetaQA/kb.ttl")
    return p.parse_args()


def slugify(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"[^a-z0-9_\-]", "", t)
    return t or "item"


def main() -> None:
    args = parse_args()
    kb_path = Path(args.kb)
    out_path = Path(args.out)

    ent = Namespace("http://metaqa.org/entity/")
    rel = Namespace("http://metaqa.org/relation/")
    ns = Namespace("http://metaqa.org/schema/")

    g = Graph()
    g.bind("ment", ent)
    g.bind("mrel", rel)
    g.bind("m", ns)

    entity_cache: dict[str, URIRef] = {}

    def ent_uri(label: str) -> URIRef:
        if label in entity_cache:
            return entity_cache[label]
        uri = URIRef(ent + slugify(label))
        entity_cache[label] = uri
        g.add((uri, ns.label, Literal(label)))
        return uri

    for line in kb_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) != 3:
            continue

        s_txt, p_txt, o_txt = parts
        s = ent_uri(s_txt)
        p = URIRef(rel + slugify(p_txt))

        # Heuristic: keep years and numeric-ish values as literals, otherwise entities.
        if o_txt.isdigit():
            o = Literal(int(o_txt))
        else:
            o = ent_uri(o_txt)

        g.add((s, p, o))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(out_path), format="turtle")
    print(f"Wrote {len(g)} triples to {out_path}")


if __name__ == "__main__":
    main()
