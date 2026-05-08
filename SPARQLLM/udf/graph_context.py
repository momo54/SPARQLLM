from __future__ import annotations

from typing import Any

from rdflib import Graph, URIRef

from SPARQLLM.entity_graph_core import to_text
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.read_rdf import get_last_loaded_graph_uri
from SPARQLLM.utils.utils import named_graph_exists


def existing_graph_uri(term: Any) -> URIRef | None:
    if term is None:
        return None
    raw = to_text(term)
    if not raw:
        return None
    try:
        uri = URIRef(raw)
    except Exception:
        return None
    if named_graph_exists(store, uri) and len(store.get_context(uri)) > 0:
        return uri
    return None


def resolve_source_graph_uri(candidate: Any = None) -> URIRef:
    explicit = existing_graph_uri(candidate)
    if explicit is not None:
        return explicit

    current = get_last_loaded_graph_uri()
    if current is not None and named_graph_exists(store, current) and len(store.get_context(current)) > 0:
        return current

    raise ValueError(
        "No source graph available. Load a KB with --load or pass an explicit named graph as the first argument."
    )


def resolve_source_graph(candidate: Any = None) -> tuple[URIRef, Graph]:
    uri = resolve_source_graph_uri(candidate)
    return uri, store.get_context(uri)
