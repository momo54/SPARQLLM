from __future__ import annotations

import hashlib
from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.entity_graph_core import simrank_ranking
from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


CAND = Namespace("http://example.org/cand#")


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _to_float(term: Any, default: float) -> float:
    try:
        return float(str(term))
    except Exception:
        return default


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:simrank:{prefix}:{digest}")

def SIMRANK(*args: Any) -> Any:
    """Compute SimRank scores from one center node.

    Supported signatures:
      - ggf:SIMRANK(center_iri, decay=0.8, max_iter=5, top_k=10, max_nodes=200)
      - ggf:SIMRANK(g_source, center_iri, decay=0.8, max_iter=5, top_k=10, max_nodes=200)
    """
    if not 1 <= len(args) <= 6:
        raise ValueError(
            "SIMRANK expects either (center[, decay[, max_iter[, top_k[, max_nodes]]]]) or "
            "(g_source, center[, decay[, max_iter[, top_k[, max_nodes]]]])"
        )

    if len(args) >= 2 and existing_graph_uri(args[0]) is not None:
        g_uri, src = resolve_source_graph(args[0])
        center = URIRef(_to_text(args[1]))
        c = min(max(_to_float(args[2], 0.8), 0.0), 1.0) if len(args) >= 3 else 0.8
        n_iter = max(1, _to_int(args[3], 5)) if len(args) >= 4 else 5
        limit = max(1, _to_int(args[4], 10)) if len(args) >= 5 else 10
        node_cap = max(2, _to_int(args[5], 200)) if len(args) >= 6 else 200
    else:
        g_uri, src = resolve_source_graph()
        center = URIRef(_to_text(args[0]))
        c = min(max(_to_float(args[1], 0.8), 0.0), 1.0) if len(args) >= 2 else 0.8
        n_iter = max(1, _to_int(args[2], 5)) if len(args) >= 3 else 5
        limit = max(1, _to_int(args[3], 10)) if len(args) >= 4 else 10
        node_cap = max(2, _to_int(args[4], 200)) if len(args) >= 5 else 200

    out_uri = _graph_uri(
        "result",
        [str(g_uri), str(center), str(c), str(n_iter), str(limit), str(node_cap)],
    )
    out = store.get_context(out_uri)
    out.bind("cand", CAND)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, CAND.SimRankResult))
    out.add((root, CAND["center"], center))
    out.add((root, CAND.decay, Literal(round(c, 6), datatype=XSD.decimal)))
    out.add((root, CAND.iterations, Literal(n_iter, datatype=XSD.integer)))

    ranked = simrank_ranking(src, str(center), c, n_iter, limit, node_cap)
    for rank, (node, score) in enumerate(ranked, start=1):
        n = BNode()
        out.add((n, RDF.type, CAND.SimRankNode))
        out.add((n, CAND.entity, URIRef(node)))
        out.add((n, CAND.score, Literal(round(score, 6), datatype=XSD.decimal)))
        out.add((n, CAND.rank, Literal(rank, datatype=XSD.integer)))
        out.add((root, CAND.candidate, n))

    return out_uri
