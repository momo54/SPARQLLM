from datetime import datetime, timezone
import hashlib
import time
import logging
from typing import Any, List, Tuple

import requests
from rdflib import Graph, URIRef, Literal, Namespace, XSD
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


# ---------------------------------------------------------------------------
# WIKIDATA_SCHEMA_TYPED  — typed/class-level neighbourhood schema
# ---------------------------------------------------------------------------

_PREFIXES_TYPED = """
PREFIX wd:       <http://www.wikidata.org/entity/>
PREFIX wdt:      <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd:       <http://www.bigdata.com/rdf#>
"""


def _edge_node_uri(entity: URIRef, prop: str, class_iri: str, direction: str) -> URIRef:
    """Stable, compact URI for an edge-pattern node."""
    key = f"{entity}|{prop}|{class_iri}|{direction}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return URIRef(f"urn:sparqllm:edge:{h}")


def _fetch_entity_types(entity: URIRef, lang: str) -> list:
    q = _PREFIXES_TYPED + f"""
SELECT DISTINCT ?type ?typeLabel WHERE {{
  VALUES ?ent {{ <{entity}> }}
  ?ent wdt:P31 ?type .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
}}"""
    try:
        return _run_wikidata_sparql(q)
    except Exception as e:
        logger.error("WIKIDATA_SCHEMA_TYPED: entity-types query failed: %s", e)
        return []


def _fetch_typed_edges(entity: URIRef, lang: str, limit: int, direction: str) -> list:
    """Return distinct (property, objectClass/subjectClass, count) rows.

    direction: 'out' → entity is subject; 'in' → entity is object.
    """
    if direction == "out":
        pattern = f"VALUES ?ent {{ <{entity}> }} ?ent ?p ?neighbor ."
        optional = "OPTIONAL { ?neighbor wdt:P31 ?neighborType . }"
    else:
        pattern = f"VALUES ?ent {{ <{entity}> }} ?neighbor ?p ?ent ."
        optional = "OPTIONAL { ?neighbor wdt:P31 ?neighborType . }"

    q = _PREFIXES_TYPED + f"""
SELECT ?p ?pLabel ?pDescription ?neighborType ?neighborTypeLabel ?neighborTypeDescription (COUNT(DISTINCT ?neighbor) AS ?cnt) WHERE {{
  {pattern}
  FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
  {optional}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
}} GROUP BY ?p ?pLabel ?pDescription ?neighborType ?neighborTypeLabel ?neighborTypeDescription
ORDER BY DESC(?cnt)
LIMIT {limit}"""
    try:
        return _run_wikidata_sparql(q)
    except Exception as e:
        logger.error("WIKIDATA_SCHEMA_TYPED: %s query failed: %s", direction, e)
        return []


def WIKIDATA_SCHEMA_TYPED(
    entity_iri: Any,
    lang: Any = "en",
    limit_out: Any = 40,
    limit_in: Any = 25,
) -> Any:
    """GGF-style UDF: build a type-level (class-level) schema around a Wikidata entity.

    Instead of raw facts, this UDF returns the **distinct classes** of neighbours
    reachable via each property, together with edge cardinalities.  This gives a
    compact, schema-like view useful for prompting LLMs or for meta-queries.

    Parameters:
      - entity_iri : IRI or Q-id (e.g. wd:Q42 or "Q42")
      - lang       : preferred label language (default "en")
      - limit_out  : max outgoing (property, object-class) patterns (default 40)
      - limit_in   : max incoming (property, subject-class) patterns (default 25)

    Graph structure produced:
      ?schema  a cand:TypedSchema ; cand:center ?entity ; cand:entityType ?type .
      ?edge    a cand:OutEdgePattern ;          # or cand:InEdgePattern
               cand:property ?p ;
               cand:propertyLabel "..." ;
               cand:neighborClass ?cls ;        # may be absent if class unknown
               cand:neighborClassLabel "..." ;
               cand:count ?n .

    Returns: named graph IRI in the shared store.
    """
    _call_start = time.perf_counter()

    entity = _normalize_entity_iri(entity_iri)
    lang_str = str(lang) if lang is not None else "en"
    try:
        lout = int(str(limit_out))
    except Exception:
        lout = 40
    try:
        lin = int(str(limit_in))
    except Exception:
        lin = 25

    logger.info(
        "WIKIDATA_SCHEMA_TYPED: entity=%s lang=%s limit_out=%d limit_in=%d",
        entity, lang_str, lout, lin,
    )

    gname = URIRef(str(entity) + "#schemaTyped")
    g: Graph = store.get_context(gname)

    # --- schema root node ---
    schema_node = URIRef(str(gname) + "#root")
    g.add((schema_node, RDF.type, CAND["TypedSchema"]))
    g.add((schema_node, CAND["center"], entity))

    # --- entity types (P31) ---
    for row in _fetch_entity_types(entity, lang_str):
        type_iri = URIRef(row["type"]["value"])
        type_label = row.get("typeLabel", {}).get("value", "")
        g.add((schema_node, CAND["entityType"], type_iri))
        if type_label:
            g.add((type_iri, RDFS.label, Literal(type_label)))

    # --- outgoing edge patterns ---
    for row in _fetch_typed_edges(entity, lang_str, lout, "out"):
        prop = URIRef(row["p"]["value"])
        prop_label = row.get("pLabel", {}).get("value", "")
        prop_desc = row.get("pDescription", {}).get("value", "")
        cls = URIRef(row["neighborType"]["value"]) if "neighborType" in row else None
        cls_label = row.get("neighborTypeLabel", {}).get("value", "")
        cls_desc = row.get("neighborTypeDescription", {}).get("value", "")
        cnt = int(row.get("cnt", {}).get("value", 1))

        edge = _edge_node_uri(entity, str(prop), str(cls) if cls else "", "out")
        g.add((edge, RDF.type, CAND["OutEdgePattern"]))
        g.add((edge, CAND["property"], prop))
        if prop_label:
            g.add((edge, CAND["propertyLabel"], Literal(prop_label)))
        if prop_desc:
            g.add((edge, CAND["propertyDescription"], Literal(prop_desc)))
        if cls:
            g.add((edge, CAND["neighborClass"], cls))
            if cls_label:
                g.add((edge, CAND["neighborClassLabel"], Literal(cls_label)))
            if cls_desc:
                g.add((edge, CAND["neighborClassDescription"], Literal(cls_desc)))
        g.add((edge, CAND["count"], Literal(cnt, datatype=XSD.integer)))
        g.add((schema_node, CAND["outEdge"], edge))

    # --- incoming edge patterns ---
    for row in _fetch_typed_edges(entity, lang_str, lin, "in"):
        prop = URIRef(row["p"]["value"])
        prop_label = row.get("pLabel", {}).get("value", "")
        prop_desc = row.get("pDescription", {}).get("value", "")
        cls = URIRef(row["neighborType"]["value"]) if "neighborType" in row else None
        cls_label = row.get("neighborTypeLabel", {}).get("value", "")
        cls_desc = row.get("neighborTypeDescription", {}).get("value", "")
        cnt = int(row.get("cnt", {}).get("value", 1))

        edge = _edge_node_uri(entity, str(prop), str(cls) if cls else "", "in")
        g.add((edge, RDF.type, CAND["InEdgePattern"]))
        g.add((edge, CAND["property"], prop))
        if prop_label:
            g.add((edge, CAND["propertyLabel"], Literal(prop_label)))
        if prop_desc:
            g.add((edge, CAND["propertyDescription"], Literal(prop_desc)))
        if cls:
            g.add((edge, CAND["neighborClass"], cls))
            if cls_label:
                g.add((edge, CAND["neighborClassLabel"], Literal(cls_label)))
            if cls_desc:
                g.add((edge, CAND["neighborClassDescription"], Literal(cls_desc)))
        g.add((edge, CAND["count"], Literal(cnt, datatype=XSD.integer)))
        g.add((schema_node, CAND["inEdge"], edge))

    _call_end = time.perf_counter()
    duration_s = _call_end - _call_start

    _attach_prov(
        g,
        gname,
        handle="wikidata",
        tool_name="wikidata.schemaTyped",
        args={
            "entity_iri": str(entity_iri),
            "lang": lang_str,
            "limit_out": lout,
            "limit_in": lin,
        },
        start_dt=datetime.now(timezone.utc),
        duration_s=duration_s,
    )

    logger.info(
        "WIKIDATA_SCHEMA_TYPED: stored %d triples in %s (%.2fs)",
        len(g), gname, duration_s,
    )
    return gname
