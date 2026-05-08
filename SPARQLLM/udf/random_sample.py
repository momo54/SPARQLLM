from __future__ import annotations

import hashlib
from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.entity_graph_core import random_sample_neighborhood, to_text
from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


CAND = Namespace("http://example.org/cand#")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:random-sample:{prefix}:{digest}")


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


def RANDOM_SAMPLE(*args: Any) -> Any:
    """Randomly sample a local neighborhood and attach cardinality estimates.

    Supported signatures:
      - ggf:RANDOM-SAMPLE(entity_iri, hops=1, direction="both", sample_rate=0.5, seed=42)
      - ggf:RANDOM-SAMPLE(g_source, entity_iri, hops=1, direction="both", sample_rate=0.5, seed=42)
    """
    if not 1 <= len(args) <= 6:
        raise ValueError(
            "RANDOM-SAMPLE expects either (entity[, hops[, direction[, sample_rate[, seed]]]]) or "
            "(g_source, entity[, hops[, direction[, sample_rate[, seed]]]])"
        )

    if len(args) >= 2 and existing_graph_uri(args[0]) is not None:
        g_uri, src = resolve_source_graph(args[0])
        center_iri = to_text(args[1])
        hop_limit = max(0, _to_int(args[2], 1)) if len(args) >= 3 else 1
        mode = to_text(args[3]).lower() if len(args) >= 4 else "both"
        rate = min(1.0, max(0.0, _to_float(args[4], 0.5))) if len(args) >= 5 else 0.5
        seed_value = _to_int(args[5], 42) if len(args) >= 6 else 42
    else:
        g_uri, src = resolve_source_graph()
        center_iri = to_text(args[0])
        hop_limit = max(0, _to_int(args[1], 1)) if len(args) >= 2 else 1
        mode = to_text(args[2]).lower() if len(args) >= 3 else "both"
        rate = min(1.0, max(0.0, _to_float(args[3], 0.5))) if len(args) >= 4 else 0.5
        seed_value = _to_int(args[4], 42) if len(args) >= 5 else 42

    mode = mode or "both"
    if mode not in {"out", "in", "both"}:
        mode = "both"
    result = random_sample_neighborhood(src, center_iri, hop_limit, mode, rate, seed_value)

    out_uri = _graph_uri(
        "result",
        [str(g_uri), center_iri, str(hop_limit), mode, str(rate), str(seed_value)],
    )
    out = store.get_context(out_uri)
    out.bind("cand", CAND)

    for triple in result.sampled_graph:
        out.add(triple)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, CAND.RandomSample))
    out.add((root, CAND["center"], URIRef(center_iri)))
    out.add((root, CAND["hops"], Literal(hop_limit, datatype=XSD.integer)))
    out.add((root, CAND["direction"], Literal(mode)))
    out.add((root, CAND["sampleRate"], Literal(result.sample_rate, datatype=XSD.double)))
    out.add((root, CAND["seed"], Literal(seed_value, datatype=XSD.integer)))
    out.add((root, CAND["exactTripleCount"], Literal(result.exact_triple_count, datatype=XSD.integer)))
    out.add((root, CAND["sampledTripleCount"], Literal(result.sampled_triple_count, datatype=XSD.integer)))
    out.add((root, CAND["estimatedTripleCount"], Literal(result.estimated_triple_count, datatype=XSD.double)))
    out.add((root, CAND["absoluteError"], Literal(result.absolute_error, datatype=XSD.double)))
    out.add((root, CAND["relativeError"], Literal(result.relative_error, datatype=XSD.double)))

    for rank, stat in enumerate(result.predicate_estimates, start=1):
        node = BNode()
        out.add((node, RDF.type, CAND.PredicateEstimate))
        out.add((node, CAND["rank"], Literal(rank, datatype=XSD.integer)))
        out.add((node, CAND["property"], URIRef(stat.property_iri)))
        out.add((node, CAND["exactFrequency"], Literal(stat.exact_frequency, datatype=XSD.integer)))
        out.add((node, CAND["sampledFrequency"], Literal(stat.sampled_frequency, datatype=XSD.integer)))
        out.add((node, CAND["estimatedFrequency"], Literal(stat.estimated_frequency, datatype=XSD.double)))
        out.add((node, CAND["absoluteError"], Literal(stat.absolute_error, datatype=XSD.double)))
        out.add((node, CAND["relativeError"], Literal(stat.relative_error, datatype=XSD.double)))
        out.add((root, CAND["predicateStat"], node))

    return out_uri
