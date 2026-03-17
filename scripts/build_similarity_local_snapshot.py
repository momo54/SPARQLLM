#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
from rdflib import Graph

WD_ENDPOINT = "https://query.wikidata.org/sparql"
JSON_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (build local similarity snapshot)",
}
TTL_HEADERS = {
    "Accept": "text/turtle",
    "User-Agent": "SPARQLLM/0.1 (build local similarity snapshot)",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build local RDF snapshot for similarity experiments")
    p.add_argument("--ref-entity", default="http://www.wikidata.org/entity/Q42")
    p.add_argument("--max-limit", type=int, default=30)
    p.add_argument("--lang", default="en")
    p.add_argument("--out-ttl", default="tmp/sf_similarity_snapshot.ttl")
    p.add_argument("--out-json", default="tmp/sf_similarity_snapshot.json")
    return p.parse_args()


def req_bytes(resp: requests.Response) -> int:
    req = resp.request
    url_b = len((req.url or "").encode("utf-8"))
    body_b = 0
    if req.body:
        body = req.body
        body_b = len(body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8"))
    return url_b + body_b


def candidates_query(ref_entity: str, limit_n: int) -> str:
    return f'''PREFIX wd:  <http://www.wikidata.org/entity/>\nPREFIX wdt: <http://www.wikidata.org/prop/direct/>\n\nSELECT ?entity ?entityLabel WHERE {{\n  ?entity wdt:P31 wd:Q5 ;\n          wdt:P106 wd:Q36180 ;\n          wdt:P136 wd:Q24925 .\n  FILTER(?entity != <{ref_entity}>)\n  BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n}}\nORDER BY ?entityLabel\nLIMIT {limit_n}\n'''


def cbd_query(entity: str, lang: str) -> str:
    return f'''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\nPREFIX schema: <https://schema.org/>\n\nCONSTRUCT {{\n  <{entity}> ?p ?o .\n  <{entity}> rdfs:label ?lbl .\n  <{entity}> schema:description ?desc .\n  ?bn ?bp ?bo .\n}} WHERE {{\n  <{entity}> ?p ?o .\n  OPTIONAL {{ <{entity}> rdfs:label ?lbl FILTER(lang(?lbl) = "{lang}") }}\n  OPTIONAL {{ <{entity}> schema:description ?desc FILTER(lang(?desc) = "{lang}") }}\n  OPTIONAL {{\n    FILTER(isBlank(?o))\n    BIND(?o AS ?bn)\n    ?bn ?bp ?bo .\n  }}\n}}\n'''


def main() -> None:
    args = parse_args()

    upload = 0
    download = 0
    calls = 0

    q = candidates_query(args.ref_entity, args.max_limit)
    r = requests.get(WD_ENDPOINT, params={"query": q}, headers=JSON_HEADERS, timeout=30)
    r.raise_for_status()
    calls += 1
    upload += req_bytes(r)
    download += len(r.content or b"")

    rows = r.json().get("results", {}).get("bindings", [])
    candidates = [
        {
            "entity": x.get("entity", {}).get("value", ""),
            "entityLabel": x.get("entityLabel", {}).get("value", ""),
        }
        for x in rows
    ]

    entities = [args.ref_entity] + [c["entity"] for c in candidates]
    merged = Graph()

    for ent in entities:
        rq = cbd_query(ent, args.lang)
        rr = requests.get(WD_ENDPOINT, params={"query": rq}, headers=TTL_HEADERS, timeout=30)
        rr.raise_for_status()
        calls += 1
        upload += req_bytes(rr)
        download += len(rr.content or b"")

        g = Graph()
        g.parse(data=rr.text, format="turtle")
        for t in g:
            merged.add(t)

    out_ttl = Path(args.out_ttl)
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    merged.serialize(destination=str(out_ttl), format="turtle")

    meta = {
        "ref_entity": args.ref_entity,
        "max_limit": args.max_limit,
        "lang": args.lang,
        "candidate_count": len(candidates),
        "entity_count": len(entities),
        "snapshot_triples": len(merged),
        "wikidata_calls": calls,
        "upload_bytes": upload,
        "download_bytes": download,
        "transfer_total_bytes": upload + download,
        "snapshot_ttl": str(out_ttl),
        "candidates": candidates,
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
