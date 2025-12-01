from datetime import datetime, timezone
import time
import logging
from typing import Any, List, Tuple

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


def _add_label_desc_triple(g: Graph, iri: URIRef, label: str = None, desc: str = None):
    if label:
        g.add((iri, RDFS.label, Literal(label)))
    if desc:
        g.add((iri, SCHEMA.description, Literal(desc)))


def _fetch_one_hop_schema(entity: URIRef, lang: str = "en", limit: int = 100) -> Graph:
    g = Graph()
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("wd", WD)
    g.bind("wdt", WDT)
    g.bind("cand", CAND)

    # Outgoing properties
    q_out = f"""
    SELECT distinct ?p ?pLabel ?o ?oLabel ?oDesc ?oType ?oTypeLabel WHERE {{
      VALUES ?s {{ <{entity}> }}
      ?s ?p ?o .
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
      OPTIONAL {{ ?o wdt:P31 ?oType . }}
      OPTIONAL {{ ?o schema:description ?oDesc FILTER(LANGMATCHES(LANG(?oDesc), "{lang}")) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
    }} LIMIT {limit}
    """

    q_out_prefixes = """
    PREFIX wd:   <http://www.wikidata.org/entity/>
    PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
    PREFIX schema: <https://schema.org/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX bd: <http://www.bigdata.com/rdf#>
    """ + q_out

    try:
        rows = _run_wikidata_sparql(q_out_prefixes)
    except Exception as e:
        logger.error("Error querying Wikidata (outgoing): %s", e)
        return g

    for b in rows:
        p = URIRef(b["p"]["value"]) if "p" in b else None
        o = URIRef(b["o"]["value"]) if "o" in b and b["o"]["type"] == "uri" else None
        p_label = b.get("pLabel", {}).get("value")
        o_label = b.get("oLabel", {}).get("value")
        o_desc = b.get("oDesc", {}).get("value")
        o_type = URIRef(b["oType"]["value"]) if "oType" in b else None
        o_type_label = b.get("oTypeLabel", {}).get("value")

        if p and o:
            # factual edge
            g.add((entity, p, o))
            # schema-style description of property and object
            _add_label_desc_triple(g, p, p_label, None)
            _add_label_desc_triple(g, o, o_label, o_desc)
            if o_type:
                g.add((o, RDF.type, o_type))
                _add_label_desc_triple(g, o_type, o_type_label, None)

    # Incoming properties
    q_in = f"""
    SELECT distinct ?s ?sLabel ?sDesc ?p ?pLabel ?sType ?sTypeLabel WHERE {{
      VALUES ?o {{ <{entity}> }}
      ?s ?p ?o .
      FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
      OPTIONAL {{ ?s wdt:P31 ?sType . }}
      OPTIONAL {{ ?s schema:description ?sDesc FILTER(LANGMATCHES(LANG(?sDesc), "{lang}")) }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
    }} LIMIT {limit}
    """

    q_in_prefixes = """
    PREFIX wd:   <http://www.wikidata.org/entity/>
    PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
    PREFIX schema: <https://schema.org/>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX bd: <http://www.bigdata.com/rdf#>
    """ + q_in

    try:
        rows_in = _run_wikidata_sparql(q_in_prefixes)
    except Exception as e:
        logger.error("Error querying Wikidata (incoming): %s", e)
        return g

    for b in rows_in:
        s = URIRef(b["s"]["value"]) if "s" in b and b["s"]["type"] == "uri" else None
        p = URIRef(b["p"]["value"]) if "p" in b else None
        s_label = b.get("sLabel", {}).get("value")
        s_desc = b.get("sDesc", {}).get("value")
        s_type = URIRef(b["sType"]["value"]) if "sType" in b else None
        s_type_label = b.get("sTypeLabel", {}).get("value")

        if s and p:
            g.add((s, p, entity))
            _add_label_desc_triple(g, p, p_label, None) if False else None
            _add_label_desc_triple(g, s, s_label, s_desc)
            if s_type:
                g.add((s, RDF.type, s_type))
                _add_label_desc_triple(g, s_type, s_type_label, None)

    # Add a summarizing node for LLM consumption
    schema_node = URIRef(str(entity) + "#localSchema")
    g.add((schema_node, RDF.type, CAND["LocalSchema"]))
    g.add((schema_node, CAND["center"], entity))

    return g


def WIKIDATA_SCHEMA_WALK(entity_iri: Any, lang: Any = "en", limit: Any = 50) -> Any:
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
