from __future__ import annotations

import hashlib
import re
from typing import Any

from rdflib import URIRef

from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:construct:{prefix}:{digest}")


def _normalize_format(fmt: str) -> str:
    value = fmt.lower().strip() or "turtle"
    aliases = {
        "ttl": "turtle",
        "nt": "nt",
        "ntriples": "nt",
        "n-triples": "nt",
    }
    return aliases.get(value, value)


def _looks_like_construct_query(text: str) -> bool:
    return bool(re.search(r"\bCONSTRUCT\b", text, flags=re.IGNORECASE) and re.search(r"\bWHERE\b", text, flags=re.IGNORECASE))


def CONSTRUCT(*args: Any) -> Any:
    """Build a named graph from inline RDF or from a SPARQL CONSTRUCT query.

    Supported signatures:
      - ggf:CONSTRUCT(construct_query)
      - ggf:CONSTRUCT(construct_query, graph_uri)
      - ggf:CONSTRUCT(g_source, construct_query)
      - ggf:CONSTRUCT(g_source, construct_query, graph_uri)
      - ggf:CONSTRUCT(rdf_text)
      - ggf:CONSTRUCT(rdf_text, format)
      - ggf:CONSTRUCT(rdf_text, format, graph_uri)

    In query mode, the SPARQL CONSTRUCT is executed against the current source
    graph (typically the KB loaded with --load) or an explicit graph URI passed
    as the first argument.

    In inline mode, the function simply parses the provided RDF payload and
    stores it as a named graph that can be queried immediately via GRAPH ?g.
    """
    if not 1 <= len(args) <= 3:
        raise ValueError(
            "CONSTRUCT expects either (construct_query[, graph_uri]), "
            "(g_source, construct_query[, graph_uri]), or "
            "(rdf_text[, format[, graph_uri]])"
        )

    # Query mode with explicit source graph:
    #   ggf:CONSTRUCT(?gSource, "CONSTRUCT { ... } WHERE { ... }"[, ?gOut])
    if len(args) >= 2 and existing_graph_uri(args[0]) is not None and _looks_like_construct_query(_to_text(args[1])):
        g_source_uri, src = resolve_source_graph(args[0])
        query_text = _to_text(args[1])
        graph_text = _to_text(args[2]) if len(args) >= 3 else ""
        graph_uri = URIRef(graph_text) if graph_text else _graph_uri("query-result", [str(g_source_uri), query_text])
        out = store.get_context(graph_uri)
        result = src.query(query_text)
        if getattr(result, "graph", None) is not None:
            for triple in result.graph:
                out.add(triple)
        return graph_uri

    # Query mode on the current --load graph:
    #   ggf:CONSTRUCT("CONSTRUCT { ... } WHERE { ... }"[, ?gOut])
    first_text = _to_text(args[0])
    if _looks_like_construct_query(first_text):
        g_source_uri, src = resolve_source_graph()
        query_text = first_text
        graph_text = _to_text(args[1]) if len(args) >= 2 else ""
        graph_uri = URIRef(graph_text) if graph_text else _graph_uri("query-result", [str(g_source_uri), query_text])
        out = store.get_context(graph_uri)
        result = src.query(query_text)
        if getattr(result, "graph", None) is not None:
            for triple in result.graph:
                out.add(triple)
        return graph_uri

    # Inline RDF mode:
    #   ggf:CONSTRUCT(rdf_text[, format[, ?gOut]])
    rdf_text = first_text
    rdf_format = _normalize_format(_to_text(args[1]) if len(args) >= 2 else "turtle")
    graph_text = _to_text(args[2]) if len(args) >= 3 else ""
    graph_uri = URIRef(graph_text) if graph_text else _graph_uri("inline-result", [rdf_text, rdf_format])
    out = store.get_context(graph_uri)
    out.parse(data=rdf_text, format=rdf_format)
    return graph_uri
