from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from pyshacl import validate
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.entity_graph_core import fetch_wikidata_cbd_graph, local_cbd_graph, normalize_wikidata_entity_iri, to_text
from SPARQLLM.udf.graph_context import resolve_source_graph
from SPARQLLM.udf.SPARQLLM import store

logger = logging.getLogger(__name__)

SCHEMA = Namespace("https://schema.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")
CAND = Namespace("http://example.org/cand#")
WD = Namespace("http://www.wikidata.org/entity/")

def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    key = "|".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:cbdshacl:{prefix}:{digest}")


def _normalize_entity_iri(entity_iri: Any) -> URIRef:
    return URIRef(normalize_wikidata_entity_iri(entity_iri))


def _resolve_shape_graph(shape_file_or_graph: Any) -> Graph:
    ref = to_text(shape_file_or_graph)

    # 1) If ref matches an existing named graph in store, use it.
    try:
        g_ctx = store.get_context(URIRef(ref))
        if len(g_ctx) > 0:
            g = Graph()
            for t in g_ctx:
                g.add(t)
            return g
    except Exception:
        pass

    # 2) Otherwise parse as file path or URI.
    p = Path(ref)
    if not p.is_absolute():
        p = Path.cwd() / p

    g = Graph()
    if p.exists():
        g.parse(str(p), format="turtle")
        return g

    # Fallback: let rdflib try URI parsing.
    g.parse(ref, format="turtle")
    return g


def CBD(entity_iri: Any, lang: Any = "en") -> Any:
    """Build a CBD graph for the current local KB, or fall back to Wikidata.

    Local mode:
      - uses the current graph loaded with `--load`
      - returns outgoing triples of the entity plus recursive blank-node closure

    Remote mode:
      - if no local graph is available, falls back to the Wikidata CBD behavior
    """
    entity_text = to_text(entity_iri)
    lang_str = to_text(lang) or "en"

    try:
        g_src_uri, g_src = resolve_source_graph()
        local_mode = True
    except Exception:
        g_src_uri = None
        g_src = None
        local_mode = False

    if local_mode:
        entity = URIRef(entity_text)
        g_uri = _graph_uri("local-cbd", [str(g_src_uri), entity_text])
        g_target = store.get_context(g_uri)
        g_target.bind("schema", SCHEMA)
        g_target.bind("cand", CAND)

        try:
            for triple in local_cbd_graph(g_src, entity_text):
                g_target.add(triple)
        except Exception as exc:
            logger.error("[CBD local] error for %s: %s", entity, exc)
        return g_uri

    entity = _normalize_entity_iri(entity_iri)
    g_uri = _graph_uri("cbd", [str(entity), lang_str])
    g_target = store.get_context(g_uri)
    g_target.bind("schema", SCHEMA)
    g_target.bind("cand", CAND)

    try:
        fetched, _, _ = fetch_wikidata_cbd_graph(str(entity), lang_str)
        for triple in fetched:
            g_target.add(triple)

        meta = URIRef(str(g_uri) + "#meta")
        g_target.add((meta, RDF.type, CAND.CBDGraph))
        g_target.add((meta, CAND["center"], entity))
        g_target.add((meta, CAND.language, Literal(lang_str)))

    except Exception as exc:
        logger.error("[CBD] error for %s: %s", entity, exc)

    return g_uri


def SHACL_VALIDATE(g_data: Any, shape_file_or_graph: Any) -> Any:
    """Validate a named graph against SHACL shapes from a file (or graph URI).

    Parameters
    ----------
    g_data: URIRef of the named data graph in store
    shape_file_or_graph: file path (e.g. "data/person-shape.ttl") or graph URI

    Returns
    -------
    URIRef of a named graph containing the SHACL validation report graph,
    plus metadata triples:
      <report#meta> cand:conforms true|false ; schema:text "...".
    """
    data_uri = URIRef(to_text(g_data))
    shape_ref = to_text(shape_file_or_graph)

    data_graph = store.get_context(data_uri)
    shape_graph = _resolve_shape_graph(shape_ref)

    report_uri = _graph_uri("shacl_report", [str(data_uri), shape_ref])
    report_ctx = store.get_context(report_uri)
    report_ctx.bind("sh", SH)
    report_ctx.bind("schema", SCHEMA)
    report_ctx.bind("cand", CAND)

    try:
        conforms, report_graph, report_text = validate(
            data_graph,
            shacl_graph=shape_graph,
            inference="rdfs",
            abort_on_first=False,
            meta_shacl=False,
            advanced=True,
            debug=False,
        )

        for triple in report_graph:
            report_ctx.add(triple)

        meta = URIRef(str(report_uri) + "#meta")
        report_ctx.add((meta, RDF.type, CAND.ShaclReport))
        report_ctx.add((meta, CAND.conforms, Literal(bool(conforms), datatype=XSD.boolean)))
        report_ctx.add((meta, SCHEMA.text, Literal(str(report_text))))

    except Exception as exc:
        logger.error("[SHACL_VALIDATE] error: %s", exc)
        meta = URIRef(str(report_uri) + "#meta")
        report_ctx.add((meta, RDF.type, CAND.ShaclReport))
        report_ctx.add((meta, CAND.conforms, Literal(False, datatype=XSD.boolean)))
        report_ctx.add((meta, SCHEMA.text, Literal(f"Validation failed: {exc}")))

    return report_uri
