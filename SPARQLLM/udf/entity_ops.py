"""entity_ops.py — Entity-centric algebraic operators for SPARQLLM.

Two UDFs:

  ENTITY(mention, lang, limit)
    Unified entity resolution: label string → Wikidata IRI.
    Returns a named graph with cand:ResolvedEntity nodes (ranked by match quality).
    Use the first cand:isBest=true node for downstream operators.

  COMPARE(e1, e2, lang, limit_props)
    Structural comparison of two Wikidata entities.
    Returns a named graph with:
      - cand:SharedProperty  — properties both entities share, with their values
      - cand:DifferingProperty — properties where the values differ
      - cand:similarityScore on the root comparison node
    Typical SPARQL usage:
      GRAPH ?gCmp {
        ?p a cand:SharedProperty    ; cand:label ?lbl ; cand:value1 ?v1 .
        ?p a cand:DifferingProperty ; cand:label ?lbl ; cand:value1 ?v1 ; cand:value2 ?v2 .
      }
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from SPARQLLM.entity_graph_core import compare_centered_graphs
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.mcp.providers.wikidata_provider import WikidataProvider

logger = logging.getLogger(__name__)

# ── Namespaces ────────────────────────────────────────────────────────────────
CAND = Namespace("http://example.org/cand#")
WD   = Namespace("http://www.wikidata.org/entity/")
WDT  = Namespace("http://www.wikidata.org/prop/direct/")

_WD_SPARQL = "https://query.wikidata.org/sparql"
_WD_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (entity-ops)",
}

_PREFIXES = """
PREFIX wd:       <http://www.wikidata.org/entity/>
PREFIX wdt:      <http://www.wikidata.org/prop/direct/>
PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema:   <https://schema.org/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd:       <http://www.bigdata.com/rdf#>
"""


# ── Internal helpers ──────────────────────────────────────────────────────────

def _uri(prefix: str, *parts: str) -> URIRef:
    key = "|".join(parts)
    h = hashlib.sha256(key.encode()).hexdigest()[:16]
    return URIRef(f"urn:sparqllm:{prefix}:{h}")


def _to_str(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _normalize_iri(raw: Any) -> str:
    s = _to_str(raw)
    if s.startswith("Q") and s[1:].isdigit():
        return f"http://www.wikidata.org/entity/{s}"
    return s


def _sparql(query: str) -> list[dict]:
    try:
        resp = requests.get(_WD_SPARQL, params={"query": query},
                            headers=_WD_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get("results", {}).get("bindings", [])
    except Exception as exc:
        logger.warning("[entity_ops] SPARQL error: %s", exc)
        return []


def _new_graph(g_uri: URIRef) -> Graph:
    g = store.get_context(g_uri)
    g.bind("cand", CAND)
    return g


# ── ENTITY ───────────────────────────────────────────────────────────────────

def ENTITY(mention: Any, lang: Any = "en", limit: Any = 5) -> Any:
    """Resolve a natural-language mention to Wikidata entities.

    This is the uniform entry-point for entity resolution in the entity-centric
    operator family.  It wraps WikidataProvider.tool_search_entities and adds
    exact-label boosting so that the best match carries cand:isBest=true.

    Parameters
    ----------
    mention : string label to look up (e.g. "Isaac Asimov")
    lang    : preferred language code (default "en")
    limit   : max candidates to return (default 5)

    Graph structure
    ---------------
    ?root   a cand:EntityResolution ;
            cand:mention "Isaac Asimov" ;
            cand:candidate ?node .

    ?node   a cand:ResolvedEntity ;
            cand:entity  <http://www.wikidata.org/entity/Q34981> ;
            cand:label   "Isaac Asimov" ;
            cand:description "American author" ;
            cand:rank    1 ;
            cand:score   1.0 ;
            cand:isBest  true .      ← only on the top-ranked node

    Returns
    -------
    URIRef of the named graph.
    """
    mention_str = _to_str(mention)
    lang_str    = _to_str(lang) or "en"
    limit_int   = max(1, _to_int(limit, 5))

    g_uri = _uri("entity", mention_str, lang_str, str(limit_int))
    g     = _new_graph(g_uri)

    root = URIRef(str(g_uri) + "#root")
    g.add((root, RDF.type,      CAND.EntityResolution))
    g.add((root, CAND.mention,  Literal(mention_str)))

    # ── call Wikidata search ──────────────────────────────────────────────────
    provider = WikidataProvider()
    result   = provider.tool_search_entities(search=mention_str,
                                             language=lang_str,
                                             limit=limit_int)
    if "error" in result:
        logger.warning("[ENTITY] Wikidata search error for '%s': %s", mention_str, result["error"])
        return g_uri

    items = result.get("jsonld", {}).get("schema:dataFeedElement", [])

    mention_lower = mention_str.lower()
    best_idx      = None   # index of the best candidate (exact-label match wins)

    candidates: list[dict] = []
    for it in items:
        item = it.get("schema:item", {}) if isinstance(it, dict) else {}
        iri   = str(item.get("@id", "")).strip()
        lab   = item.get("rdfs:label", {})
        label = lab.get("@value", "") if isinstance(lab, dict) else str(lab)
        desc  = str(item.get("schema:description", "")).strip()
        pos   = int(it.get("schema:position", len(candidates) + 1))
        candidates.append({"iri": iri, "label": label, "desc": desc, "pos": pos})

    # Exact-label match gets rank 1
    for i, c in enumerate(candidates):
        if c["label"].lower() == mention_lower:
            best_idx = i
            break
    if best_idx is None and candidates:
        best_idx = 0

    for rank, cand in enumerate(candidates, start=1):
        score = 1.0 / float(rank)
        node  = BNode()
        g.add((node, RDF.type,          CAND.ResolvedEntity))
        g.add((node, CAND.entity,       URIRef(cand["iri"])))
        g.add((node, CAND.label,        Literal(cand["label"])))
        g.add((node, CAND.rank,         Literal(rank, datatype=XSD.integer)))
        g.add((node, CAND.score,        Literal(round(score, 6), datatype=XSD.decimal)))
        if cand["desc"]:
            g.add((node, CAND.description, Literal(cand["desc"])))
        if rank - 1 == best_idx:
            g.add((node, CAND.isBest, Literal(True, datatype=XSD.boolean)))
        g.add((root, CAND.candidate, node))

    logger.info("[ENTITY] '%s' → %d candidates in %s", mention_str, len(candidates), g_uri)
    return g_uri


# ── COMPARE ──────────────────────────────────────────────────────────────────

def COMPARE(e1: Any, e2: Any, lang: Any = "en", limit_props: Any = 60) -> Any:
    """Structural comparison of two Wikidata entities.

    Fetches the direct properties (wdt:Pxxx) of both entities and partitions
    them into three groups:

      cand:SharedProperty   — property with at least one *identical* value in both
      cand:DifferingProperty — property present in both but with different values
      cand:ExclusiveProperty — property present in only one of the two entities

    Parameters
    ----------
    e1, e2       : Wikidata entity IRIs or Q-ids (e.g. wd:Q42 or "Q42")
    lang         : preferred label language (default "en")
    limit_props  : max properties to fetch per entity (default 60)

    Graph structure
    ---------------
    ?root  a cand:Comparison ;
           cand:entity1 <...> ; cand:entity2 <...> ;
           cand:entity1Label "..." ; cand:entity2Label "..." ;
           cand:sharedCount ?n ; cand:differingCount ?m ; cand:exclusiveCount ?k ;
           cand:similarityScore ?score .

    Per property node:
      ?pnode  a cand:SharedProperty | cand:DifferingProperty | cand:ExclusiveProperty ;
              cand:property      <wdt:Pxxx> ;
              cand:propertyLabel "..." ;
              cand:value1        <IRI or literal> ;   ← value from e1 (if present)
              cand:value1Label   "..." ;
              cand:value2        <IRI or literal> ;   ← value from e2 (if present)
              cand:value2Label   "..." ;
              cand:exclusiveOf   "entity1" | "entity2" . ← only for ExclusiveProperty

    Returns
    -------
    URIRef of the named graph.
    """
    iri1     = _normalize_iri(e1)
    iri2     = _normalize_iri(e2)
    lang_str = _to_str(lang) or "en"
    lim      = max(1, _to_int(limit_props, 60))

    g_uri = _uri("compare", iri1, iri2, lang_str)
    g     = _new_graph(g_uri)

    # ── fetch properties per entity — two separate queries to guarantee `lim`
    # rows each (a single VALUES + LIMIT would skew toward one entity) ─────────
    def _fetch_props(iri: str) -> dict[str, list[dict]]:
        q = _PREFIXES + f"""
SELECT ?p ?pLabel ?o ?oLabel WHERE {{
  <{iri}> ?p ?o .
  FILTER(STRSTARTS(STR(?p), "http://www.wikidata.org/prop/direct/"))
  FILTER(!isBLANK(?o))
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "{lang_str}".
  }}
}}
LIMIT {lim}
"""
        bucket: dict[str, list[dict]] = {}
        for row in _sparql(q):
            p_val  = row.get("p",      {}).get("value", "")
            p_lbl  = row.get("pLabel", {}).get("value", "")
            o_row  = row.get("o",      {})
            o_lbl  = row.get("oLabel", {}).get("value", "")
            o_val  = o_row.get("value", "")
            o_type = o_row.get("type",  "uri")
            o_obj  = URIRef(o_val) if o_type == "uri" else Literal(o_val)
            if p_val not in bucket:
                bucket[p_val] = []
            bucket[p_val].append({"o": o_obj, "oLabel": o_lbl, "pLabel": p_lbl})
        return bucket

    props1 = _fetch_props(iri1)
    props2 = _fetch_props(iri2)

    label1 = label2 = ""

    # ── fetch entity labels separately (wikibase:label on ?ent itself) ────────
    q_labels = _PREFIXES + f"""
SELECT ?ent ?entLabel WHERE {{
  VALUES ?ent {{ <{iri1}> <{iri2}> }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang_str}". }}
}}
"""
    for row in _sparql(q_labels):
        ent_val = row.get("ent", {}).get("value", "")
        lbl     = row.get("entLabel", {}).get("value", "")
        if ent_val == iri1:
            label1 = lbl
        elif ent_val == iri2:
            label2 = lbl

    # ── classify properties ───────────────────────────────────────────────────
    all_props = set(props1) | set(props2)

    shared_count    = 0
    differing_count = 0
    exclusive_count = 0

    for p_iri in all_props:
        p_vals1 = props1.get(p_iri, [])
        p_vals2 = props2.get(p_iri, [])
        p_label = (p_vals1 or p_vals2)[0]["pLabel"] if (p_vals1 or p_vals2) else ""

        o_set1  = {str(v["o"]) for v in p_vals1}
        o_set2  = {str(v["o"]) for v in p_vals2}

        pnode = BNode()
        g.add((pnode, CAND.property,      URIRef(p_iri)))
        if p_label:
            g.add((pnode, CAND.propertyLabel, Literal(p_label)))

        # Attach values for e1
        for v in p_vals1:
            g.add((pnode, CAND.value1, v["o"]))
            if v["oLabel"]:
                g.add((pnode, CAND.value1Label, Literal(v["oLabel"])))

        # Attach values for e2
        for v in p_vals2:
            g.add((pnode, CAND.value2, v["o"]))
            if v["oLabel"]:
                g.add((pnode, CAND.value2Label, Literal(v["oLabel"])))

        if p_vals1 and p_vals2:
            shared_vals = o_set1 & o_set2
            if shared_vals:
                g.add((pnode, RDF.type, CAND.SharedProperty))
                shared_count += 1
            else:
                g.add((pnode, RDF.type, CAND.DifferingProperty))
                differing_count += 1
        elif p_vals1:
            g.add((pnode, RDF.type,          CAND.ExclusiveProperty))
            g.add((pnode, CAND.exclusiveOf,  Literal("entity1")))
            exclusive_count += 1
        else:
            g.add((pnode, RDF.type,          CAND.ExclusiveProperty))
            g.add((pnode, CAND.exclusiveOf,  Literal("entity2")))
            exclusive_count += 1

    # ── root summary node ─────────────────────────────────────────────────────
    root = URIRef(str(g_uri) + "#root")
    g.add((root, RDF.type,          CAND.Comparison))
    g.add((root, CAND.entity1,      URIRef(iri1)))
    g.add((root, CAND.entity2,      URIRef(iri2)))
    if label1:
        g.add((root, CAND.entity1Label, Literal(label1)))
    if label2:
        g.add((root, CAND.entity2Label, Literal(label2)))
    total_compared = shared_count + differing_count + exclusive_count
    similarity = 0.0 if total_compared == 0 else shared_count / float(total_compared)

    g.add((root, CAND.sharedCount,    Literal(shared_count,    datatype=XSD.integer)))
    g.add((root, CAND.differingCount, Literal(differing_count, datatype=XSD.integer)))
    g.add((root, CAND.exclusiveCount, Literal(exclusive_count, datatype=XSD.integer)))
    g.add((root, CAND.similarityScore, Literal(round(similarity, 6), datatype=XSD.decimal)))

    logger.info(
        "[COMPARE] %s vs %s → shared=%d differing=%d exclusive=%d similarity=%.4f",
        iri1, iri2, shared_count, differing_count, exclusive_count, similarity,
    )
    return g_uri


def COMPARE_GRAPHS(g1: Any, g2: Any, e1: Any, e2: Any) -> Any:
    """Compare two existing named graphs around two center entities.

    Unlike COMPARE(e1,e2,...) which fetches data from Wikidata, this operator
    only reads local named graphs already materialized in the store (e.g. CBD,
    ESBM summaries). This keeps intermediate data server-side.

    Parameters
    ----------
    g1, g2 : named graph URIs
    e1, e2 : center entities in g1 and g2

    Returns
    -------
    URIRef of the comparison graph, with cand:Comparison root and
    cand:SharedProperty / cand:DifferingProperty / cand:ExclusiveProperty nodes.
    """
    g1_uri = URIRef(_to_str(g1))
    g2_uri = URIRef(_to_str(g2))
    iri1 = _normalize_iri(e1)
    iri2 = _normalize_iri(e2)

    src1 = store.get_context(g1_uri)
    src2 = store.get_context(g2_uri)

    out_uri = _uri("compare-graphs", str(g1_uri), str(g2_uri), iri1, iri2)
    out = _new_graph(out_uri)

    c1 = URIRef(iri1)
    c2 = URIRef(iri2)
    cmp = compare_centered_graphs(src1, src2, iri1, iri2)

    for prop in cmp.properties:

        pnode = BNode()
        out.add((pnode, CAND.property, URIRef(prop.property_iri)))

        # Persist value tokens as literals for debug/inspection.
        for tok in prop.value1_tokens:
            out.add((pnode, CAND.value1, Literal(tok)))
        for tok in prop.value2_tokens:
            out.add((pnode, CAND.value2, Literal(tok)))

        if prop.kind == "shared":
            out.add((pnode, CAND.valueOverlap, Literal(True, datatype=XSD.boolean)))
            out.add((pnode, RDF.type, CAND.SharedProperty))
        elif prop.kind == "differing":
            out.add((pnode, CAND.valueOverlap, Literal(False, datatype=XSD.boolean)))
            out.add((pnode, RDF.type, CAND.DifferingProperty))
        elif prop.kind == "exclusive_entity1":
            out.add((pnode, RDF.type, CAND.ExclusiveProperty))
            out.add((pnode, CAND.exclusiveOf, Literal("entity1")))
        else:
            out.add((pnode, RDF.type, CAND.ExclusiveProperty))
            out.add((pnode, CAND.exclusiveOf, Literal("entity2")))

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, CAND.Comparison))
    out.add((root, CAND.entity1, c1))
    out.add((root, CAND.entity2, c2))
    out.add((root, CAND.graph1, g1_uri))
    out.add((root, CAND.graph2, g2_uri))
    out.add((root, CAND.sharedCount, Literal(cmp.shared_count, datatype=XSD.integer)))
    out.add((root, CAND.differingCount, Literal(cmp.differing_count, datatype=XSD.integer)))
    out.add((root, CAND.exclusiveCount, Literal(cmp.exclusive_count, datatype=XSD.integer)))
    out.add((root, CAND.similarityScore, Literal(cmp.similarity_score, datatype=XSD.decimal)))

    logger.info(
        "[COMPARE_GRAPHS] g1=%s g2=%s → shared=%d differing=%d exclusive=%d similarity=%.4f",
        g1_uri, g2_uri, cmp.shared_count, cmp.differing_count, cmp.exclusive_count, cmp.similarity_score,
    )
    return out_uri
