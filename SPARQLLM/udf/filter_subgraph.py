from __future__ import annotations

import hashlib
from typing import Any

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.entity_graph_core import filter_subgraph, to_text
from SPARQLLM.udf.SPARQLLM import store


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:filter-subgraph:{prefix}:{digest}")


def _parse_csv_set(term: Any) -> set[str]:
    raw = to_text(term)
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _to_bool(term: Any, default: bool = True) -> bool:
    raw = to_text(term).lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return default


def FILTER_SUBGRAPH(
    g_source: Any,
    predicate_csv: Any = "",
    node_csv: Any = "",
    node_mode: Any = "touch",
    keep_literals: Any = True,
) -> Any:
    """Filter an explicit source graph by predicate and/or node constraints."""
    g_uri = URIRef(to_text(g_source))
    pred_filter = _parse_csv_set(predicate_csv)
    node_filter = _parse_csv_set(node_csv)
    mode = to_text(node_mode).lower() or "touch"
    keep_lits = _to_bool(keep_literals, True)
    src = store.get_context(g_uri)
    filtered = filter_subgraph(src, pred_filter, node_filter, mode, keep_lits)

    out_uri = _graph_uri(
        "result",
        [str(g_uri), ",".join(sorted(pred_filter)), ",".join(sorted(node_filter)), mode, str(keep_lits)],
    )
    out = store.get_context(out_uri)
    for triple in filtered:
        out.add(triple)

    meta = URIRef(str(out_uri) + "#meta")
    out.add((meta, RDF.type, URIRef("http://example.org/cand#FilteredSubgraph")))
    out.add((meta, URIRef("http://example.org/cand#sourceGraph"), g_uri))
    out.add((meta, URIRef("http://example.org/cand#tripleCount"), Literal(len(filtered), datatype=XSD.integer)))
    return out_uri
