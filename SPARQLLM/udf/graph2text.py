from __future__ import annotations

import hashlib
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from SPARQLLM.entity_graph_core import METAQA_LABEL_PRED, to_text
from SPARQLLM.udf.graph_context import resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store


SCHEMA = Namespace("https://schema.org/")
CAND = Namespace("http://example.org/cand#")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:graph2text:{prefix}:{digest}")


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _label_for(source: Graph, node: URIRef) -> str:
    rdfs_labels = sorted({str(obj) for obj in source.objects(node, RDFS.label) if str(obj)})
    if rdfs_labels:
        return rdfs_labels[0]

    schema_names = sorted({str(obj) for obj in source.objects(node, SCHEMA.name) if str(obj)})
    if schema_names:
        return schema_names[0]

    metaqa_labels = sorted({str(obj) for obj in source.objects(node, METAQA_LABEL_PRED) if str(obj)})
    if metaqa_labels:
        return metaqa_labels[0]

    return ""


def _compact_iri(node: URIRef) -> str:
    text = str(node)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rsplit("/", 1)[-1]
    return text


def _render_node(source: Graph, node: Any) -> str:
    if isinstance(node, URIRef):
        label = _label_for(source, node)
        return label or _compact_iri(node)
    return str(node)


def graph_to_text(source: Graph, max_triples: int = 25) -> str:
    ordered = sorted(source, key=lambda triple: (str(triple[0]), str(triple[1]), str(triple[2])))
    lines: list[str] = []
    seen: set[str] = set()

    for subj, pred, obj in ordered:
        line = f"{_render_node(source, subj)} | {_render_node(source, pred)} | {_render_node(source, obj)}"
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= max_triples:
            break

    remaining = max(0, len(ordered) - len(lines))
    if remaining:
        lines.append(f"... ({remaining} more triple(s))")

    return "\n".join(lines)


def GRAPH2TEXT(*args: Any) -> Any:
    """Render a named graph as a compact textual context.

    Supported signatures:
      - ggf:GRAPH2TEXT(g_source)
      - ggf:GRAPH2TEXT(g_source, max_triples)
    """
    if not 1 <= len(args) <= 2:
        raise ValueError("GRAPH2TEXT expects (g_source[, max_triples])")

    g_src_uri, src = resolve_source_graph(args[0])
    max_triples = max(1, _to_int(args[1], 25)) if len(args) >= 2 else 25

    out_uri = _graph_uri("rendered", [str(g_src_uri), str(max_triples)])
    out = store.get_context(out_uri)
    out.bind("schema", SCHEMA)
    out.bind("cand", CAND)

    text = graph_to_text(src, max_triples=max_triples)
    rendered_count = min(max_triples, len(src))

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, SCHEMA.CreativeWork))
    out.add((root, SCHEMA.name, Literal(f"Text view of {g_src_uri}")))
    out.add((root, SCHEMA.text, Literal(text)))
    out.add((root, CAND.sourceGraph, g_src_uri))
    out.add((root, CAND.tripleCount, Literal(len(src), datatype=XSD.integer)))
    out.add((root, CAND.renderedTripleCount, Literal(rendered_count, datatype=XSD.integer)))

    return out_uri
