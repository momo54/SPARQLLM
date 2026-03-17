from __future__ import annotations

from typing import Any

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.beam_search import (
    BEAM_EXPAND_RELATED,
    CAND,
    _add_beam_node,
    _beam_nodes,
    _extract_mentions,
    _graph_uri,
    _new_beam_graph,
    _to_int,
    _to_text,
)
from SPARQLLM.udf.mcp.providers.wikidata_provider import WikidataProvider


def _meta_node(g_uri: URIRef) -> URIRef:
    return URIRef(str(g_uri) + "#meta")


def _pick_best_candidate(mention: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None

    lowered = mention.strip().lower()
    for item in items:
        label = str(item.get("label", "")).strip().lower()
        if label == lowered:
            return item

    return items[0]


def _extract_entity_from_graph(g_term: Any) -> tuple[str | None, int]:
    g = store.get_context(g_term)
    call_count = 0
    for _, _, obj in g.triples((_meta_node(g.identifier), CAND.wikidataCallCount, None)):
        try:
            call_count = int(str(obj))
        except Exception:
            call_count = 0

    for node in g.subjects(RDF.type, CAND.BeamNode):
        is_best = False
        for _, _, flag in g.triples((node, CAND.isBest, None)):
            if str(flag).lower() == "true":
                is_best = True
                break
        if not is_best:
            continue
        for _, _, entity in g.triples((node, CAND.entity, None)):
            return str(entity), call_count

    nodes = _beam_nodes(g)
    if not nodes:
        return None, call_count

    best = nodes[0]
    entity = best.get("entity")
    return (str(entity) if entity else None), call_count


def STRUCTGPT_LINK(question: Any, top_k_expand: Any = 5) -> Any:
    """StructGPT-like entity linking for an anchor mention.

    Strategy:
    1. extract the most salient mention from the question
    2. call Wikidata search once
    3. keep the best candidate in a named graph
    """
    text = _to_text(question)
    expand_k = max(1, _to_int(top_k_expand, 5))
    mentions = _extract_mentions(text)
    mention = mentions[0] if mentions else text

    provider = WikidataProvider()
    result = provider.tool_search_entities(search=mention, language="en", limit=expand_k)
    items = result.get("search", []) if isinstance(result, dict) else []

    # Provider returns JSON-LD under jsonld; convert to a simple candidate list.
    if not items and isinstance(result, dict):
        jsonld = result.get("jsonld", {})
        feed_items = jsonld.get("schema:dataFeedElement", []) if isinstance(jsonld, dict) else []
        items = []
        for feed_item in feed_items:
            inner = feed_item.get("schema:item", {}) if isinstance(feed_item, dict) else {}
            label_obj = inner.get("rdfs:label", {}) if isinstance(inner, dict) else {}
            items.append(
                {
                    "id": str(inner.get("@id", "")).rsplit("/", 1)[-1],
                    "entity": str(inner.get("@id", "")),
                    "label": label_obj.get("@value", mention) if isinstance(label_obj, dict) else mention,
                    "position": feed_item.get("schema:position", 1),
                }
            )

    chosen = _pick_best_candidate(mention, items)

    g_uri = _graph_uri("structgpt_link", [text, mention, str(expand_k)])
    g = _new_beam_graph(g_uri, text, iteration=0)
    meta = _meta_node(g_uri)
    g.add((meta, CAND.action, Literal("link_entity")))
    g.add((meta, CAND.anchorMention, Literal(mention)))
    g.add((meta, CAND.wikidataCallCount, Literal(1, datatype=XSD.integer)))

    if not chosen:
        return g_uri

    qid = str(chosen.get("id", "")).strip()
    entity_iri = str(chosen.get("entity", "")).strip() or f"http://www.wikidata.org/entity/{qid}"
    label = str(chosen.get("label", mention)).strip() or mention
    try:
        position = int(chosen.get("position", 1))
    except Exception:
        position = 1
    score = 1.0 / float(max(position, 1))

    node = _add_beam_node(
        g,
        mention=mention,
        depth=0,
        score=score,
        entity_iri=entity_iri,
        label=label,
        reason="structgpt_link",
    )
    g.add((node, CAND.isBest, Literal(True, datatype=XSD.boolean)))
    return g_uri


def STRUCTGPT_EXPAND_RELATED(g_link_or_entity: Any, question: Any, limit: Any = 10) -> Any:
    """Expand an anchor entity toward related entities.

    Accepts either a graph returned by STRUCTGPT_LINK or a direct entity IRI/QID.
    Carries a cumulative `cand:wikidataCallCount` for comparison reporting.
    """
    text = _to_text(question)
    max_k = max(1, _to_int(limit, 10))

    input_text = _to_text(g_link_or_entity)
    if input_text.startswith("urn:"):
        entity_iri, previous_calls = _extract_entity_from_graph(g_link_or_entity)
    else:
        entity_iri, previous_calls = input_text, 0

    if not entity_iri:
        g_uri = _graph_uri("structgpt_expand", [text, "empty", str(max_k)])
        g = _new_beam_graph(g_uri, text, iteration=1)
        g.add((_meta_node(g_uri), CAND.wikidataCallCount, Literal(previous_calls, datatype=XSD.integer)))
        return g_uri

    g_related = BEAM_EXPAND_RELATED(entity_iri, text, max_k)
    related_graph = store.get_context(g_related)
    nodes = _beam_nodes(related_graph)

    g_uri = _graph_uri("structgpt_expand", [text, entity_iri, str(max_k)])
    g = _new_beam_graph(g_uri, text, iteration=1)
    meta = _meta_node(g_uri)
    g.add((meta, CAND.action, Literal("expand_related")))
    g.add((meta, CAND.anchorEntity, URIRef(entity_iri)))
    g.add((meta, CAND.wikidataCallCount, Literal(previous_calls + 1, datatype=XSD.integer)))

    for cand in nodes:
        _add_beam_node(
            g,
            mention=str(cand.get("mention") or cand.get("label") or ""),
            depth=int(cand.get("depth") or 1),
            score=float(cand.get("score") or 0.0),
            entity_iri=str(cand.get("entity")) if cand.get("entity") else None,
            label=str(cand.get("label") or cand.get("mention") or ""),
            reason="structgpt_expand_related",
        )

    return g_uri


def STRUCTGPT_ANSWER(question: Any, g_candidates: Any, top_k: Any = 5) -> Any:
    """Materialize a compact answer graph from candidate entities."""
    text = _to_text(question)
    keep_k = max(1, _to_int(top_k, 5))
    in_graph = store.get_context(g_candidates)
    nodes = _beam_nodes(in_graph)[:keep_k]

    total_calls = 0
    for _, _, obj in in_graph.triples((_meta_node(in_graph.identifier), CAND.wikidataCallCount, None)):
        try:
            total_calls = int(str(obj))
        except Exception:
            total_calls = 0

    labels = [str(node.get("label") or node.get("mention") or "") for node in nodes]
    labels = [label for label in labels if label]
    answer_text = (
        f"Similar entities for the question are: {', '.join(labels[:keep_k])}."
        if labels
        else "No related entities found."
    )

    g_uri = _graph_uri("structgpt_answer", [text, str(g_candidates), str(keep_k)])
    g = _new_beam_graph(g_uri, text, iteration=2)
    meta = _meta_node(g_uri)
    g.add((meta, CAND.action, Literal("answer")))
    g.add((meta, CAND.wikidataCallCount, Literal(total_calls, datatype=XSD.integer)))

    answer_node = URIRef(str(g_uri) + "#answer")
    g.add((answer_node, RDF.type, CAND.StructGPTAnswer))
    g.add((answer_node, CAND.text, Literal(answer_text)))
    g.add((answer_node, CAND.question, Literal(text)))
    g.add((answer_node, CAND.wikidataCallCount, Literal(total_calls, datatype=XSD.integer)))

    for rank, cand in enumerate(nodes, start=1):
        node = _add_beam_node(
            g,
            mention=str(cand.get("mention") or cand.get("label") or ""),
            depth=int(cand.get("depth") or 1),
            score=float(cand.get("score") or 0.0),
            entity_iri=str(cand.get("entity")) if cand.get("entity") else None,
            label=str(cand.get("label") or cand.get("mention") or ""),
            reason="structgpt_answer_candidate",
        )
        g.add((node, CAND.rank, Literal(rank, datatype=XSD.integer)))
        g.add((answer_node, CAND.candidate, node))

    return g_uri