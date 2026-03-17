#!/usr/bin/env python3
"""
Evaluate non-GGF orchestrated ESBM baselines.

This script emulates a client-side orchestration workflow:
1) Retrieve candidate triples with SPARQL SELECT.
2) Rank/select in Python (random or degree/frequency).
3) Evaluate against gold summaries.

Compared to in-engine graph manipulation, this baseline helps quantify
orchestration overhead and data shipping.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from rdflib import Graph

Triple = Tuple[str, str, str]
GoldMap = Dict[str, Set[Triple]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate orchestrated non-GGF ESBM baselines")
    parser.add_argument("--graph", required=True, help="Path to KG file (ttl/nt/nq/trig/rdf/jsonld)")
    parser.add_argument("--gold", required=True, help="Path to gold summaries file (json/jsonl/csv)")
    parser.add_argument("--k", type=int, default=10, help="Summary size per entity")
    parser.add_argument(
        "--baselines",
        nargs="+",
        choices=["random", "degree"],
        default=["random", "degree"],
        help="Baselines to run",
    )
    parser.add_argument(
        "--neighborhood",
        choices=["out", "in", "both"],
        default="out",
        help="Candidate triple neighborhood around entity",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--out-json",
        default="out/esbm_orchestrated_baselines_results.json",
        help="Output JSON path",
    )
    return parser.parse_args()


def guess_format(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".ttl":
        return "turtle"
    if ext == ".nt":
        return "nt"
    if ext == ".nq":
        return "nquads"
    if ext == ".trig":
        return "trig"
    if ext in {".rdf", ".xml"}:
        return "xml"
    if ext == ".jsonld":
        return "json-ld"
    return None


def parse_gold(path: Path) -> GoldMap:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_gold_json(path)
    if suffix == ".jsonl":
        return _parse_gold_jsonl(path)
    if suffix == ".csv":
        return _parse_gold_csv(path)
    raise ValueError(f"Unsupported gold format: {path}")


def _normalize_triple(raw: Sequence[str]) -> Triple:
    if len(raw) != 3:
        raise ValueError(f"Expected triple of len 3, got: {raw}")
    s, p, o = raw
    return str(s), str(p), str(o)


def _parse_gold_json(path: Path) -> GoldMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: GoldMap = {}
    for entity, triples in data.items():
        out[str(entity)] = {_normalize_triple(t) for t in triples}
    return out


def _parse_gold_jsonl(path: Path) -> GoldMap:
    out: GoldMap = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            entity = str(row["entity"])
            triples = {_normalize_triple(t) for t in row["triples"]}
            if entity in out:
                out[entity].update(triples)
            else:
                out[entity] = triples
    return out


def _parse_gold_csv(path: Path) -> GoldMap:
    out: GoldMap = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"entity", "s", "p", "o"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV gold file missing required columns: {sorted(missing)}")
        for row in reader:
            entity = str(row["entity"])
            triple: Triple = (str(row["s"]), str(row["p"]), str(row["o"]))
            if entity in out:
                out[entity].add(triple)
            else:
                out[entity] = {triple}
    return out


def load_graph(graph_path: Path) -> Graph:
    g = Graph()
    g.parse(graph_path, format=guess_format(graph_path))
    return g


def is_iri(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def sparql_escape_iri(iri: str) -> str:
    return f"<{iri}>"


def query_predicate_counts(g: Graph) -> Tuple[Counter, float]:
    query = """
SELECT ?p (COUNT(*) AS ?cnt)
WHERE {
  ?s ?p ?o .
}
GROUP BY ?p
"""
    started = time.perf_counter()
    rows = list(g.query(query))
    elapsed = time.perf_counter() - started

    counts: Counter = Counter()
    for row in rows:
        p = str(row[0])
        cnt = int(row[1])
        counts[p] = cnt
    return counts, elapsed


def query_candidates(g: Graph, entity: str, neighborhood: str) -> Tuple[List[Triple], float]:
    e = sparql_escape_iri(entity)

    if neighborhood == "out":
        query = f"""
SELECT ?s ?p ?o
WHERE {{
  BIND({e} AS ?s)
  ?s ?p ?o .
}}
"""
    elif neighborhood == "in":
        query = f"""
SELECT ?s ?p ?o
WHERE {{
  BIND({e} AS ?o)
  ?s ?p ?o .
}}
"""
    else:
        query = f"""
SELECT DISTINCT ?s ?p ?o
WHERE {{
  {{
    BIND({e} AS ?s)
    ?s ?p ?o .
  }}
  UNION
  {{
    BIND({e} AS ?o)
    ?s ?p ?o .
  }}
}}
"""

    started = time.perf_counter()
    rows = list(g.query(query))
    elapsed = time.perf_counter() - started

    triples: List[Triple] = []
    for s, p, o in rows:
        triples.append((str(s), str(p), str(o)))
    return triples, elapsed


def run_random_baseline(cands: List[Triple], k: int, rng: random.Random) -> List[Triple]:
    if len(cands) <= k:
        return list(cands)
    return rng.sample(cands, k)


def run_degree_baseline(cands: List[Triple], pred_counts: Counter, k: int) -> List[Triple]:
    scored: List[Tuple[float, Triple]] = []
    for triple in cands:
        pred = triple[1]
        freq = pred_counts.get(pred, 1)
        score = 1.0 / float(freq)
        scored.append((score, triple))

    scored.sort(key=lambda x: (x[0], x[1][1], x[1][2]), reverse=True)
    return [triple for _, triple in scored[:k]]


def compute_prf(pred: Iterable[Triple], gold: Set[Triple]) -> Dict[str, float]:
    pred_set = set(pred)
    tp = len(pred_set & gold)
    fp = len(pred_set - gold)
    fn = len(gold - pred_set)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def approx_triples_payload_bytes(triples: Iterable[Triple]) -> int:
    total = 0
    for s, p, o in triples:
        total += len(s.encode("utf-8")) + len(p.encode("utf-8")) + len(o.encode("utf-8"))
    return total


def evaluate(
    baseline_name: str,
    entities: List[str],
    gold_map: GoldMap,
    entity_candidates: Dict[str, List[Triple]],
    pred_counts: Counter,
    k: int,
    seed: int,
) -> Dict:
    rng = random.Random(seed)
    per_entity: Dict[str, Dict[str, float]] = {}

    sum_tp = 0
    sum_fp = 0
    sum_fn = 0

    for entity in entities:
        cands = entity_candidates.get(entity, [])
        if baseline_name == "random":
            pred = run_random_baseline(cands, k, rng)
        elif baseline_name == "degree":
            pred = run_degree_baseline(cands, pred_counts, k)
        else:
            raise ValueError(f"Unknown baseline: {baseline_name}")

        metrics = compute_prf(pred, gold_map[entity])
        per_entity[entity] = metrics

        sum_tp += metrics["tp"]
        sum_fp += metrics["fp"]
        sum_fn += metrics["fn"]

    micro_p = sum_tp / (sum_tp + sum_fp) if (sum_tp + sum_fp) else 0.0
    micro_r = sum_tp / (sum_tp + sum_fn) if (sum_tp + sum_fn) else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    macro_p = sum(v["precision"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0
    macro_r = sum(v["recall"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0
    macro_f1 = sum(v["f1"] for v in per_entity.values()) / len(per_entity) if per_entity else 0.0

    return {
        "baseline": f"orchestrated_{baseline_name}",
        "k": k,
        "n_entities": len(entities),
        "micro": {
            "precision": micro_p,
            "recall": micro_r,
            "f1": micro_f1,
            "tp": sum_tp,
            "fp": sum_fp,
            "fn": sum_fn,
        },
        "macro": {
            "precision": macro_p,
            "recall": macro_r,
            "f1": macro_f1,
        },
        "per_entity": per_entity,
    }


def main() -> None:
    args = parse_args()

    graph_path = Path(args.graph)
    gold_path = Path(args.gold)
    out_path = Path(args.out_json)

    kg = load_graph(graph_path)
    gold_map = parse_gold(gold_path)

    all_entities = sorted(gold_map.keys())
    valid_entities = [e for e in all_entities if is_iri(e)]
    skipped_entities = [e for e in all_entities if not is_iri(e)]

    pred_counts, pred_count_query_s = query_predicate_counts(kg)

    entity_candidates: Dict[str, List[Triple]] = {}
    candidate_query_total_s = 0.0
    extracted_triples_total = 0
    extracted_payload_bytes = 0
    sparql_query_count = 1  # global predicate count query

    for entity in valid_entities:
        cands, elapsed = query_candidates(kg, entity, args.neighborhood)
        entity_candidates[entity] = cands

        candidate_query_total_s += elapsed
        extracted_triples_total += len(cands)
        extracted_payload_bytes += approx_triples_payload_bytes(cands)
        sparql_query_count += 1

    results = {
        "config": {
            "graph": str(graph_path),
            "gold": str(gold_path),
            "k": args.k,
            "neighborhood": args.neighborhood,
            "seed": args.seed,
            "baselines": args.baselines,
            "n_triples_graph": len(kg),
            "n_entities_total": len(all_entities),
            "n_entities_evaluated": len(valid_entities),
            "n_entities_skipped": len(skipped_entities),
        },
        "orchestration_metrics": {
            "sparql_query_count": sparql_query_count,
            "pred_count_query_s": round(pred_count_query_s, 6),
            "candidate_query_total_s": round(candidate_query_total_s, 6),
            "candidate_query_avg_s": round(candidate_query_total_s / len(valid_entities), 6) if valid_entities else 0.0,
            "extracted_triples_total": extracted_triples_total,
            "extracted_payload_bytes_approx": extracted_payload_bytes,
            "external_steps_per_entity": 2,
        },
        "skipped_entities": skipped_entities,
        "results": {},
    }

    for baseline_name in args.baselines:
        results["results"][baseline_name] = evaluate(
            baseline_name=baseline_name,
            entities=valid_entities,
            gold_map=gold_map,
            entity_candidates=entity_candidates,
            pred_counts=pred_counts,
            k=args.k,
            seed=args.seed,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_path),
                "n_entities_evaluated": len(valid_entities),
                "orchestration_metrics": results["orchestration_metrics"],
                "baselines": {
                    name: {
                        "micro_f1": results["results"][name]["micro"]["f1"],
                        "macro_f1": results["results"][name]["macro"]["f1"],
                    }
                    for name in results["results"]
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
