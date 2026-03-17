#!/usr/bin/env python3
"""
Evaluate simple ESBM-like entity summarization baselines.

Implemented baselines:
- random-k
- degree-frequency-k

Input assumptions:
1) A knowledge graph file readable by RDFLib (ttl, nt, nq, trig, rdf/xml, json-ld).
2) A gold file describing summary triples per entity, in one of:
   - JSON: {"<entity_uri>": [[s,p,o], [s,p,o], ...], ...}
   - JSONL: one object per line with fields:
       {"entity": "...", "triples": [[s,p,o], ...]}
   - CSV: columns entity,s,p,o

The script computes per-entity and global precision/recall/f1 at triple level.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from rdflib import Graph

Triple = Tuple[str, str, str]
GoldMap = Dict[str, Set[Triple]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate simple ESBM baselines")
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
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for random baseline",
    )
    parser.add_argument(
        "--out-json",
        default="out/esbm_baselines_results.json",
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
    if ext == ".rdf" or ext == ".xml":
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


def build_indexes(g: Graph) -> Tuple[Dict[str, List[Triple]], Dict[str, List[Triple]], Counter]:
    outgoing: Dict[str, List[Triple]] = {}
    incoming: Dict[str, List[Triple]] = {}
    pred_counts: Counter = Counter()

    for s, p, o in g:
        ts: Triple = (str(s), str(p), str(o))
        s_key = str(s)
        o_key = str(o)
        if s_key in outgoing:
            outgoing[s_key].append(ts)
        else:
            outgoing[s_key] = [ts]
        if o_key in incoming:
            incoming[o_key].append(ts)
        else:
            incoming[o_key] = [ts]
        pred_counts[str(p)] += 1

    return outgoing, incoming, pred_counts


def candidates_for_entity(
    entity: str,
    outgoing: Dict[str, List[Triple]],
    incoming: Dict[str, List[Triple]],
    neighborhood: str,
) -> List[Triple]:
    out_cands = outgoing.get(entity, [])
    in_cands = incoming.get(entity, [])

    if neighborhood == "out":
        return list(dict.fromkeys(out_cands))
    if neighborhood == "in":
        return list(dict.fromkeys(in_cands))
    return list(dict.fromkeys(out_cands + in_cands))


def run_random_baseline(cands: List[Triple], k: int, rng: random.Random) -> List[Triple]:
    if len(cands) <= k:
        return list(cands)
    return rng.sample(cands, k)


def run_degree_frequency_baseline(cands: List[Triple], pred_counts: Counter, k: int) -> List[Triple]:
    # Predicate rarity gives higher score to informative relations.
    scored: List[Tuple[float, Triple]] = []
    for t in cands:
        pred = t[1]
        freq = pred_counts.get(pred, 1)
        score = 1.0 / float(freq)
        scored.append((score, t))
    scored.sort(key=lambda x: (x[0], x[1][1], x[1][2]), reverse=True)
    return [t for _, t in scored[:k]]


def compute_prf(pred: Iterable[Triple], gold: Set[Triple]) -> Dict[str, float]:
    pred_set = set(pred)
    tp = len(pred_set & gold)
    fp = len(pred_set - gold)
    fn = len(gold - pred_set)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_baseline(
    name: str,
    entities: List[str],
    gold_map: GoldMap,
    outgoing: Dict[str, List[Triple]],
    incoming: Dict[str, List[Triple]],
    pred_counts: Counter,
    k: int,
    neighborhood: str,
    seed: int,
) -> Dict:
    rng = random.Random(seed)
    per_entity: Dict[str, Dict[str, float]] = {}

    sum_tp = 0
    sum_fp = 0
    sum_fn = 0

    for entity in entities:
        cands = candidates_for_entity(entity, outgoing, incoming, neighborhood)
        if name == "random":
            pred = run_random_baseline(cands, k, rng)
        elif name == "degree":
            pred = run_degree_frequency_baseline(cands, pred_counts, k)
        else:
            raise ValueError(f"Unknown baseline: {name}")

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
        "baseline": name,
        "k": k,
        "neighborhood": neighborhood,
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
    entities = sorted(gold_map.keys())

    outgoing, incoming, pred_counts = build_indexes(kg)

    results = {
        "config": {
            "graph": str(graph_path),
            "gold": str(gold_path),
            "k": args.k,
            "neighborhood": args.neighborhood,
            "seed": args.seed,
            "baselines": args.baselines,
            "n_triples_graph": len(kg),
            "n_entities": len(entities),
        },
        "results": {},
    }

    for baseline_name in args.baselines:
        results["results"][baseline_name] = evaluate_baseline(
            name=baseline_name,
            entities=entities,
            gold_map=gold_map,
            outgoing=outgoing,
            incoming=incoming,
            pred_counts=pred_counts,
            k=args.k,
            neighborhood=args.neighborhood,
            seed=args.seed,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "out_json": str(out_path),
        "config": results["config"],
        "baselines": {
            name: {
                "micro_f1": results["results"][name]["micro"]["f1"],
                "macro_f1": results["results"][name]["macro"]["f1"],
            }
            for name in results["results"]
        },
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
