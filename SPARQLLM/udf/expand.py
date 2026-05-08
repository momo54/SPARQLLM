from __future__ import annotations

import hashlib
from typing import Any

from rdflib import URIRef

from SPARQLLM.entity_graph_core import expand_neighborhood_graph, to_text
from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:expand:{prefix}:{digest}")


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def EXPAND(*args: Any) -> Any:
    """Expand a graph around one center entity up to k hops.

    Supported signatures:
      - ggf:EXPAND(entity_iri, hops=1, direction="both")
      - ggf:EXPAND(g_source, entity_iri, hops=1, direction="both")
    """
    if not 1 <= len(args) <= 4:
        raise ValueError("EXPAND expects either (entity[, hops[, direction]]) or (g_source, entity[, hops[, direction]])")

    if len(args) >= 2 and existing_graph_uri(args[0]) is not None:
        g_uri, src = resolve_source_graph(args[0])
        entity = to_text(args[1])
        hop_count = max(0, _to_int(args[2], 1)) if len(args) >= 3 else 1
        mode = to_text(args[3]).lower() if len(args) >= 4 else "both"
    else:
        g_uri, src = resolve_source_graph()
        entity = to_text(args[0])
        hop_count = max(0, _to_int(args[1], 1)) if len(args) >= 2 else 1
        mode = to_text(args[2]).lower() if len(args) >= 3 else "both"

    mode = mode or "both"
    expanded = expand_neighborhood_graph(src, [entity], hop_count, mode)

    out_uri = _graph_uri("neighborhood", [str(g_uri), entity, str(hop_count), mode])
    out = store.get_context(out_uri)
    for triple in expanded:
        out.add(triple)
    return out_uri
