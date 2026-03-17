from __future__ import annotations

import hashlib
import random
from collections import Counter
from typing import Any

from rdflib import Graph, URIRef

from SPARQLLM.udf.SPARQLLM import store


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:esbm:{prefix}:{digest}")


def _as_graph(term: Any) -> Graph:
    return store.get_context(URIRef(_to_text(term)))


def _candidate_triples(source: Graph, entity: str, neighborhood: str) -> list[tuple]:
    out = []
    if neighborhood in ("out", "both"):
        out.extend((s, p, o) for (s, p, o) in source.triples((URIRef(entity), None, None)))
    if neighborhood in ("in", "both"):
        out.extend((s, p, o) for (s, p, o) in source.triples((None, None, URIRef(entity))))

    # stable dedup preserving order
    seen = set()
    dedup = []
    for t in out:
        key = (str(t[0]), str(t[1]), str(t[2]))
        if key not in seen:
            seen.add(key)
            dedup.append(t)
    return dedup


def candidate_triples(source: Graph, entity: str, neighborhood: str) -> list[tuple]:
    return _candidate_triples(source, entity, neighborhood)


def _rank_degree(cands: list[tuple], pred_counts: Counter, k: int) -> list[tuple]:
    scored = []
    for s, p, o in cands:
        freq = pred_counts.get(str(p), 1)
        score = 1.0 / float(freq)
        scored.append((score, str(p), str(o), (s, p, o)))
    scored.sort(reverse=True)
    return [t[-1] for t in scored[:k]]


def _rank_random(cands: list[tuple], k: int, seed: int) -> list[tuple]:
    if len(cands) <= k:
        return list(cands)
    rng = random.Random(seed)
    return rng.sample(cands, k)


def select_summary_triples(
    source: Graph,
    entity: str,
    k: int,
    neighborhood: str,
    mode: str,
    seed: int,
) -> list[tuple]:
    cands = _candidate_triples(source, entity, neighborhood)
    if not cands:
        return []

    if mode == "random":
        return _rank_random(cands, k, seed)

    pred_counts = Counter(str(p) for (_, p, _) in source)
    return _rank_degree(cands, pred_counts, k)


def ESBM_SUMMARY(
    g_source: Any,
    entity_iri: Any,
    k: Any = 10,
    neighborhood: Any = "out",
    mode: Any = "degree",
    seed: Any = 42,
) -> Any:
    """Generate a top-k entity summary graph from a source graph.

    Parameters
    ----------
    g_source:
        Named graph URI holding the source KG.
    entity_iri:
        Center entity IRI (http/https).
    k:
        Number of triples to keep.
    neighborhood:
        "out" | "in" | "both".
    mode:
        "degree" (predicate rarity score 1/freq) | "random".
    seed:
        Used only in random mode.

    Returns
    -------
    URIRef of a named graph containing only selected summary triples.
    """
    src = _as_graph(g_source)
    entity = _to_text(entity_iri)
    k_int = max(1, _to_int(k, 10))
    nb = _to_text(neighborhood).lower() or "out"
    rank_mode = _to_text(mode).lower() or "degree"
    seed_int = _to_int(seed, 42)

    if nb not in {"out", "in", "both"}:
        nb = "out"

    cands = _candidate_triples(src, entity, nb)
    if not cands:
        out_uri = _graph_uri("summary", [str(g_source), entity, str(k_int), nb, rank_mode, str(seed_int), "empty"])
        return out_uri

    selected = select_summary_triples(src, entity, k_int, nb, rank_mode, seed_int)

    out_uri = _graph_uri("summary", [str(g_source), entity, str(k_int), nb, rank_mode, str(seed_int)])
    out = store.get_context(out_uri)
    for triple in selected:
        out.add(triple)
    return out_uri
