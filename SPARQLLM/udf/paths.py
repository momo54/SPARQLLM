from __future__ import annotations

import hashlib
from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.entity_graph_core import shortest_paths, to_text
from SPARQLLM.udf.graph_context import existing_graph_uri, resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


SLM = Namespace("http://sparqllm/slm#")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:paths:{prefix}:{digest}")


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def PATHS(*args: Any) -> Any:
    """Return a graph encoding shortest paths between two nodes.

    Supported signatures:
      - ggf:PATHS(start_iri, goal_iri, max_depth=4, direction="out", max_paths=10)
      - ggf:PATHS(g_source, start_iri, goal_iri, max_depth=4, direction="out", max_paths=10)
    """
    if not 2 <= len(args) <= 6:
        raise ValueError(
            "PATHS expects either (start, goal[, max_depth[, direction[, max_paths]]]) or "
            "(g_source, start, goal[, max_depth[, direction[, max_paths]]])"
        )

    if len(args) >= 3 and existing_graph_uri(args[0]) is not None:
        g_uri, src = resolve_source_graph(args[0])
        start = to_text(args[1])
        goal = to_text(args[2])
        depth = max(0, _to_int(args[3], 4)) if len(args) >= 4 else 4
        mode = to_text(args[4]).lower() if len(args) >= 5 else "out"
        path_cap = max(1, _to_int(args[5], 10)) if len(args) >= 6 else 10
    else:
        g_uri, src = resolve_source_graph()
        start = to_text(args[0])
        goal = to_text(args[1])
        depth = max(0, _to_int(args[2], 4)) if len(args) >= 3 else 4
        mode = to_text(args[3]).lower() if len(args) >= 4 else "out"
        path_cap = max(1, _to_int(args[4], 10)) if len(args) >= 5 else 10

    mode = mode or "out"
    paths = shortest_paths(src, start, goal, depth, mode, path_cap)

    out_uri = _graph_uri("result", [str(g_uri), start, goal, str(depth), mode, str(path_cap)])
    out = store.get_context(out_uri)
    out.bind("slm", SLM)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, SLM.PathSet))
    out.add((root, SLM.start, URIRef(start)))
    out.add((root, SLM.goal, URIRef(goal)))
    out.add((root, SLM.pathCount, Literal(len(paths), datatype=XSD.integer)))

    for path_index, path in enumerate(paths, start=1):
        path_node = BNode()
        out.add((path_node, RDF.type, SLM.Path))
        out.add((path_node, SLM.rank, Literal(path_index, datatype=XSD.integer)))
        out.add((path_node, SLM.length, Literal(len(path), datatype=XSD.integer)))
        out.add((root, SLM.hasPath, path_node))

        for step_index, (src_node, pred, dst_node) in enumerate(path, start=1):
            step = BNode()
            out.add((step, RDF.type, SLM.PathStep))
            out.add((step, SLM.pos, Literal(step_index, datatype=XSD.integer)))
            out.add((step, SLM.src, src_node))
            out.add((step, SLM.pred, pred))
            out.add((step, SLM.dst, dst_node))
            out.add((path_node, SLM.hasStep, step))

    return out_uri
