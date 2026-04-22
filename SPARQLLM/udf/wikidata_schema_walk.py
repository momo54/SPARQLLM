# pyright: reportMissingImports=false, reportMissingModuleSource=false

from datetime import datetime, timezone
import time
import logging
from typing import Any, List

import requests
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, RDFS

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.mcp.slm_mcp_tool import _attach_prov

logger = logging.getLogger(__name__)

SCHEMA = Namespace("https://schema.org/")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")
CAND = Namespace("http://example.org/cand#")

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "SPARQLLM/0.1 (schema-walk)"
PREFIXES = """
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX schema: <https://schema.org/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd: <http://www.bigdata.com/rdf#>
"""


def _normalize_entity_iri(entity_iri: Any) -> URIRef:
    if isinstance(entity_iri, URIRef):
        return entity_iri
    s = str(entity_iri)
    # Accept plain Q-id and expand
    if s.startswith("Q"):
        return WD[s]
    return URIRef(s)


def _run_wikidata_sparql(query: str) -> List[dict]:
    headers = {"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT}
    resp = requests.get(WIKIDATA_SPARQL_ENDPOINT, params={"query": query}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", {}).get("bindings", [])


def _query_with_prefixes(body: str) -> List[dict]:
    return _run_wikidata_sparql(PREFIXES + body)


def _uri_binding(binding: dict, key: str) -> URIRef | None:
    cell = binding.get(key)
    if not cell or cell.get("type") != "uri":
        return None
    return URIRef(cell.get("value"))


def _literal_binding(binding: dict, key: str) -> str | None:
    cell = binding.get(key)
    if not cell:
        return None
    return cell.get("value")


def _add_label_desc_triple(g: Graph, iri: URIRef, label: str | None = None, desc: str | None = None):
    if label:
        g.add((iri, RDFS.label, Literal(label)))
    if desc:
        g.add((iri, SCHEMA.description, Literal(desc)))


def _build_outgoing_query(entity: URIRef, lang: str, limit: int) -> str:
    return f"""
    SELECT distinct ?p ?pLabel ?o ?oLabel ?oDesc ?oType ?oTypeLabel WHERE {{
      VALUES ?s {{ <{entity}> }}
      ?s ?p ?o .
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
      OPTIONAL {{ ?o wdt:P31 ?oType . }}
      OPTIONAL {{ ?o schema:description ?oDesc FILTER(LANGMATCHES(LANG(?oDesc), "{lang}")) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
    }} LIMIT {limit}
    """


def _build_incoming_query(entity: URIRef, lang: str, limit: int) -> str:
    return f"""
    SELECT distinct ?s ?sLabel ?sDesc ?p ?pLabel ?sType ?sTypeLabel WHERE {{
      VALUES ?o {{ <{entity}> }}
      ?s ?p ?o .
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
      OPTIONAL {{ ?s wdt:P31 ?sType . }}
      OPTIONAL {{ ?s schema:description ?sDesc FILTER(LANGMATCHES(LANG(?sDesc), "{lang}")) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
    }} LIMIT {limit}
    """


def _apply_outgoing_row(g: Graph, entity: URIRef, row: dict) -> None:
    p = _uri_binding(row, "p")
    o = _uri_binding(row, "o")
    if not p or not o:
        return

    p_label = _literal_binding(row, "pLabel")
    o_label = _literal_binding(row, "oLabel")
    o_desc = _literal_binding(row, "oDesc")
    o_type = _uri_binding(row, "oType")
    o_type_label = _literal_binding(row, "oTypeLabel")

    g.add((entity, p, o))
    _add_label_desc_triple(g, p, p_label, None)
    _add_label_desc_triple(g, o, o_label, o_desc)
    if o_type:
        g.add((o, RDF.type, o_type))
        _add_label_desc_triple(g, o_type, o_type_label, None)


def _apply_incoming_row(g: Graph, entity: URIRef, row: dict) -> None:
    s = _uri_binding(row, "s")
    p = _uri_binding(row, "p")
    if not s or not p:
        return

    s_label = _literal_binding(row, "sLabel")
    s_desc = _literal_binding(row, "sDesc")
    s_type = _uri_binding(row, "sType")
    s_type_label = _literal_binding(row, "sTypeLabel")

    g.add((s, p, entity))
    _add_label_desc_triple(g, s, s_label, s_desc)
    if s_type:
        g.add((s, RDF.type, s_type))
        _add_label_desc_triple(g, s_type, s_type_label, None)


def _fetch_rows_with_logging(query: str, direction: str) -> List[dict]:
    try:
        return _query_with_prefixes(query)
    except Exception as exc:
        logger.error("Error querying Wikidata (%s): %s", direction, exc)
        return []


def _fetch_one_hop_schema(entity: URIRef, lang: str = "en", limit: int = 100) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("cand", CAND)

    outgoing_rows = _fetch_rows_with_logging(_build_outgoing_query(entity, lang, limit), "outgoing")
    for row in outgoing_rows:
        _apply_outgoing_row(g, entity, row)

    incoming_rows = _fetch_rows_with_logging(_build_incoming_query(entity, lang, limit), "incoming")
    for row in incoming_rows:
        _apply_incoming_row(g, entity, row)

    # Add a summarizing node for LLM consumption
    schema_node = URIRef(str(entity) + "#localSchema")
    g.add((schema_node, RDF.type, CAND["LocalSchema"]))
    g.add((schema_node, CAND["center"], entity))

    return g


def wikidata_schema_walk(entity_iri: Any, lang: Any = "en", limit: Any = 50) -> Any:
    """GGF-style UDF: build a 1-hop local schema around a Wikidata entity.

    - entity_iri: IRI or Q-id string (e.g., "Q42" or <http://www.wikidata.org/entity/Q42>)
    - lang: preferred language for labels/descriptions (default "en")
    - limit: max number of edges per direction

    Returns: named graph identifier stored in the global store.
    """


    _call_start = time.perf_counter()

    entity = _normalize_entity_iri(entity_iri)
    lang_str = str(lang) if lang is not None else "en"
    try:
        limit_int = int(str(limit))
    except Exception:
        limit_int = 50

    logger.info("WIKIDATA_SCHEMA_WALK: entity=%s lang=%s limit=%s", entity, lang_str, limit_int)

    local_g = _fetch_one_hop_schema(entity, lang=lang_str, limit=limit_int)

    # Materialize into a named graph in the shared store
    gname = URIRef(str(entity) + "#schemaWalk")
    target_graph: Graph = store.get_context(gname)

    for triple in local_g:
        target_graph.add(triple)

    _call_end = time.perf_counter()
    duration_s = _call_end - _call_start

    # Annoter le graphe avec la provenance
    _attach_prov(
        target_graph,
        gname,
        handle="wikidata",
        tool_name="wikidata.schemaWalk",
        args={
            "entity_iri": entity_iri,
            "lang": lang,
            "limit": limit
        },
        start_dt=datetime.now(timezone.utc),
        duration_s=duration_s
    )

    return gname


# Keep UDF compatibility with existing config alias names.
WIKIDATA_SCHEMA_WALK = wikidata_schema_walk
