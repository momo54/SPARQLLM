#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from rdflib import Graph, URIRef

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import reset_store, store


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local-store transfer scaling (GGF vs script)")
    p.add_argument("--config", default="config.ini")
    p.add_argument("--snapshot-ttl", default="tmp/sf_similarity_snapshot.ttl")
    p.add_argument("--ref-entity", default="http://www.wikidata.org/entity/Q42")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--neighborhood", choices=["out", "in", "both"], default="both")
    p.add_argument("--mode", choices=["degree", "random"], default="degree")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limits", nargs="+", type=int, default=[10, 20, 30])
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--out-csv", default="tmp/similarity_transfer_scaling_local.csv")
    p.add_argument("--out-json", default="tmp/similarity_transfer_scaling_local.json")
    p.add_argument("--out-plot", default="plots/similarity_transfer_scaling_local.png")
    return p.parse_args()


def rows_csv_bytes(rows: list[dict[str, Any]]) -> int:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["entity", "entityLabel", "score", "shared", "differing", "exclusive"])
    for r in rows:
        w.writerow([r["entity"], r["entityLabel"], r["score"], r["shared"], r["differing"], r["exclusive"]])
    return len(buf.getvalue().encode("utf-8"))


def local_query(limit_n: int, ref_entity: str, snapshot_ttl: str, k: int, neighborhood: str, mode: str, seed: int, top_n: int) -> str:
    return f'''PREFIX wd:       <http://www.wikidata.org/entity/>\nPREFIX wdt:      <http://www.wikidata.org/prop/direct/>\nPREFIX cand:     <http://example.org/cand#>\nPREFIX ggf:      <http://ggf.org/>\n\nSELECT ?entity ?entityLabel ?score ?shared ?differing ?exclusive\nWHERE {{\n  BIND(ggf:LOAD("{snapshot_ttl}") AS ?gAll)\n  VALUES ?refEntity {{ <{ref_entity}> }}\n\n  {{\n    SELECT ?entity ?entityLabel WHERE {{\n      GRAPH ?gAll {{\n        ?entity wdt:P31 wd:Q5 ;\n                wdt:P106 wd:Q36180 ;\n                wdt:P136 wd:Q24925 .\n      }}\n      FILTER(?entity != ?refEntity)\n      BIND(REPLACE(STR(?entity), "^.*/", "") AS ?entityLabel)\n    }}\n    ORDER BY ?entityLabel\n    LIMIT {limit_n}\n  }}\n\n  BIND(ggf:ESBM-SUMMARY(?gAll, ?refEntity, {k}, "{neighborhood}", "{mode}", {seed}) AS ?gRefSummary)\n  BIND(ggf:ESBM-SUMMARY(?gAll, ?entity, {k}, "{neighborhood}", "{mode}", {seed}) AS ?gEntSummary)\n  BIND(ggf:COMPARE-GRAPHS(?gRefSummary, ?gEntSummary, ?refEntity, ?entity) AS ?gCmp)\n\n  GRAPH ?gCmp {{\n    ?root a cand:Comparison ;\n          cand:sharedCount ?shared ;\n          cand:differingCount ?differing ;\n          cand:exclusiveCount ?exclusive ;\n          cand:similarityScore ?score .\n  }}\n}}\nORDER BY DESC(?score) DESC(?shared) ?entityLabel\nLIMIT {top_n}\n'''


def parse_snapshot(path: str) -> Graph:
    g = Graph()
    g.parse(path, format="turtle")
    return g


def local_profile(source: Graph, center: str) -> dict[str, set[str]]:
    c = URIRef(center)
    prof: dict[str, set[str]] = {}
    for _, p, o in source.triples((c, None, None)):
        prof.setdefault(str(p), set()).add(f"out|{str(o)}")
    for s, p, _ in source.triples((None, None, c)):
        prof.setdefault(str(p), set()).add(f"in|{str(s)}")
    return prof


def compare_profiles(source: Graph, e1: str, e2: str) -> dict[str, Any]:
    p1 = local_profile(source, e1)
    p2 = local_profile(source, e2)
    all_p = set(p1) | set(p2)
    shared = 0
    differing = 0
    exclusive = 0
    for p in all_p:
        v1 = p1.get(p, set())
        v2 = p2.get(p, set())
        if v1 and v2:
            shared += 1
            if not (v1 & v2):
                differing += 1
        elif v1 or v2:
            exclusive += 1
    total = shared + exclusive
    score = 0.0 if total == 0 else shared / float(total)
    return {"score": round(score, 6), "shared": shared, "differing": differing, "exclusive": exclusive}


def candidates_from_snapshot(source: Graph, ref_entity: str, limit_n: int) -> list[dict[str, str]]:
    wd = "http://www.wikidata.org/entity/"
    wdt = "http://www.wikidata.org/prop/direct/"
    p31 = URIRef(wdt + "P31")
    p106 = URIRef(wdt + "P106")
    p136 = URIRef(wdt + "P136")
    q5 = URIRef(wd + "Q5")
    q36180 = URIRef(wd + "Q36180")
    q24925 = URIRef(wd + "Q24925")

    cands = []
    for s in set(source.subjects(p31, q5)):
        if str(s) == ref_entity:
            continue
        if (s, p106, q36180) in source and (s, p136, q24925) in source:
            iri = str(s)
            cands.append({"entity": iri, "entityLabel": iri.rsplit("/", 1)[-1]})
    cands.sort(key=lambda x: x["entityLabel"])
    return cands[:limit_n]


def one_entity_slice_bytes(source: Graph, entity: str) -> int:
    e = URIRef(entity)
    g = Graph()
    for t in source.triples((e, None, None)):
        g.add(t)
    for t in source.triples((None, None, e)):
        g.add(t)
    return len(g.serialize(format="turtle").encode("utf-8"))


def run_ggf(args: argparse.Namespace, limit_n: int) -> dict[str, Any]:
    query = local_query(
        limit_n=limit_n,
        ref_entity=args.ref_entity,
        snapshot_ttl=args.snapshot_ttl,
        k=args.k,
        neighborhood=args.neighborhood,
        mode=args.mode,
        seed=args.seed,
        top_n=args.top,
    )
    t0 = time.perf_counter()
    qres = list(store.query(query))
    elapsed = round(time.perf_counter() - t0, 6)

    rows = [
        {
            "entity": str(r[0]),
            "entityLabel": str(r[1]),
            "score": float(r[2]),
            "shared": int(r[3]),
            "differing": int(r[4]),
            "exclusive": int(r[5]),
        }
        for r in qres
    ]
    upload = len(query.encode("utf-8"))
    download = rows_csv_bytes(rows)
    return {
        "method": "ggf-local",
        "limit": limit_n,
        "wall_time_s": elapsed,
        "nb_calls": 1,
        "upload_bytes": upload,
        "download_bytes": download,
        "output_bytes": download,
        "transfer_total_bytes": upload + download,
    }


def run_script(args: argparse.Namespace, source: Graph, limit_n: int) -> dict[str, Any]:
    t0 = time.perf_counter()
    candidates = candidates_from_snapshot(source, args.ref_entity, limit_n)

    # Simulated client/server transfer in local triplestore setting:
    # - call 1: candidate query result shipped
    # - call 2: reference entity slice shipped once
    # - call 3..N+2: candidate entity slices shipped
    cand_bytes = rows_csv_bytes(
        [{"entity": c["entity"], "entityLabel": c["entityLabel"], "score": 0, "shared": 0, "differing": 0, "exclusive": 0} for c in candidates]
    )
    ref_bytes = one_entity_slice_bytes(source, args.ref_entity)
    cands_bytes = sum(one_entity_slice_bytes(source, c["entity"]) for c in candidates)

    rows = []
    for c in candidates:
        cmp = compare_profiles(source, args.ref_entity, c["entity"])
        rows.append(
            {
                "entity": c["entity"],
                "entityLabel": c["entityLabel"],
                "score": cmp["score"],
                "shared": cmp["shared"],
                "differing": cmp["differing"],
                "exclusive": cmp["exclusive"],
            }
        )

    rows.sort(key=lambda r: (-float(r["score"]), -int(r["shared"]), str(r["entityLabel"])))
    rows = rows[: args.top]
    out_bytes = rows_csv_bytes(rows)
    elapsed = round(time.perf_counter() - t0, 6)

    upload = 0
    download = cand_bytes + ref_bytes + cands_bytes
    return {
        "method": "script-local",
        "limit": limit_n,
        "wall_time_s": elapsed,
        "nb_calls": 2 + len(candidates),
        "upload_bytes": upload,
        "download_bytes": download,
        "output_bytes": out_bytes,
        "transfer_total_bytes": upload + download + out_bytes,
    }


def plot(path: Path, rows: list[dict[str, Any]], limits: list[int]) -> None:
    m = {r["method"]: {int(r["limit"]): r for r in rows if r["method"] in {"ggf-local", "script-local"}} for r in rows}
    g = [m["ggf-local"][l]["transfer_total_bytes"] for l in limits]
    s = [m["script-local"][l]["transfer_total_bytes"] for l in limits]
    gc = [m["ggf-local"][l]["nb_calls"] for l in limits]
    sc = [m["script-local"][l]["nb_calls"] for l in limits]

    plt.figure(figsize=(10, 4.8))
    plt.subplot(1, 2, 1)
    plt.plot(limits, g, marker="o", label="GGF-local")
    plt.plot(limits, s, marker="o", label="Script-local")
    plt.xlabel("Candidate limit")
    plt.ylabel("Transferred bytes")
    plt.title("Local-store transfer")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.subplot(1, 2, 2)
    plt.plot(limits, gc, marker="o", label="GGF-local")
    plt.plot(limits, sc, marker="o", label="Script-local")
    plt.xlabel("Candidate limit")
    plt.ylabel("Logical calls")
    plt.title("Local-store calls")
    plt.grid(alpha=0.3)
    plt.legend()

    plt.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)


def main() -> None:
    args = parse_args()
    limits = [int(x) for x in args.limits]

    ConfigSingleton.reset_instance()
    ConfigSingleton(config_file=args.config)

    source = parse_snapshot(args.snapshot_ttl)

    rows: list[dict[str, Any]] = []
    for lim in limits:
        reset_store()
        rows.append(run_ggf(args, lim))
        rows.append(run_script(args, source, lim))

    out_csv = Path(args.out_csv)
    out_json = Path(args.out_json)
    out_plot = Path(args.out_plot)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["method", "limit", "wall_time_s", "nb_calls", "upload_bytes", "download_bytes", "output_bytes", "transfer_total_bytes"],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    plot(out_plot, rows, limits)

    payload = {
        "config": {
            "snapshot_ttl": args.snapshot_ttl,
            "ref_entity": args.ref_entity,
            "limits": limits,
            "top": args.top,
            "k": args.k,
            "neighborhood": args.neighborhood,
            "mode": args.mode,
            "seed": args.seed,
        },
        "summary": rows,
        "artifacts": {
            "csv": str(out_csv),
            "json": str(out_json),
            "plot": str(out_plot),
        },
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
