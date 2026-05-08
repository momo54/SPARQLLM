import logging
from typing import Any

from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.metaqa_schema_to_sparql import (
    _answer_relation_preferences,
    _build_query_from_template,
    _graph_uri,
    _question_relation_hints,
)

logger = logging.getLogger(__name__)

CAND = Namespace("http://example.org/cand#")


def _literal_str(graph, subject, predicate) -> str:
    for _, _, obj in graph.triples((subject, predicate, None)):
        return str(obj)
    return ""


def _literal_int(graph, subject, predicate, default: int) -> int:
    value = _literal_str(graph, subject, predicate)
    try:
        return int(value)
    except Exception:
        return default


def _graph_meta(graph) -> dict[str, str]:
    meta: dict[str, str] = {"question": "", "anchor": "", "entity": "", "preferred_terminal_rel": ""}
    for gen, _, _ in graph.triples((None, RDF.type, CAND.GeneratedQuery)):
        meta["question"] = _literal_str(graph, gen, CAND.question)
        meta["anchor"] = _literal_str(graph, gen, CAND.anchor)
        meta["preferred_terminal_rel"] = _literal_str(graph, gen, CAND.viaProperty)
        for _, _, entity in graph.triples((gen, CAND.entity, None)):
            meta["entity"] = str(entity)
            break
        return meta
    return meta


def _candidate_items(graph) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for gen, _, _ in graph.triples((None, RDF.type, CAND.GeneratedQuery)):
        for _, _, node in graph.triples((gen, CAND.candidate, None)):
            template = _literal_str(graph, node, CAND.mentionText)
            if not template:
                continue
            item = {
                "node": node,
                "id": _literal_str(graph, node, CAND.templateId) or node.rsplit("#", 1)[-1],
                "rank": _literal_int(graph, node, CAND.rank, 999999),
                "hops": _literal_int(graph, node, CAND.depth, max(template.count(" ."), 1)),
                "path": _literal_str(graph, node, CAND.reason),
                "terminal_rel": _literal_str(graph, node, CAND.viaProperty),
                "path_rels": [rel for rel in _literal_str(graph, node, CAND.pathRels).split("|") if rel],
                "template": template,
            }
            items.append(item)
        break
    return items


def _ask_query(template: str) -> str:
    return (
        "PREFIX m: <http://metaqa.org/schema/>\n"
        "PREFIX ment: <http://metaqa.org/entity/>\n"
        "PREFIX mrel: <http://metaqa.org/relation/>\n"
        "ASK WHERE {\n"
        f"  {template}\n"
        "}"
    )


def _has_results(kb_graph, template: str) -> bool:
    try:
        res = kb_graph.query(_ask_query(template))
        ask_answer = getattr(res, "askAnswer", None)
        if ask_answer is not None:
            return bool(ask_answer)
        return bool(res)
    except Exception as exc:
        logger.warning("METAQA_SELECT_EXECUTABLE_QUERY ASK failed: %s", exc)
        return False


def _choose_candidate(items: list[dict[str, Any]], question: str, preferred_terminal_rel: str) -> dict[str, Any] | None:
    if not items:
        return None

    answer_prefs = _answer_relation_preferences(question)
    question_hints = _question_relation_hints(question)
    if preferred_terminal_rel and preferred_terminal_rel not in answer_prefs:
        answer_prefs = [preferred_terminal_rel] + answer_prefs

    executable = [item for item in items if item.get("has_results")]
    pool = executable or items
    return sorted(
        pool,
        key=lambda item: (
            0 if item.get("terminal_rel") in answer_prefs else 1,
            0 if question_hints.issubset(set(item.get("path_rels", []))) else 1,
            int(item.get("hops", 99)),
            int(item.get("rank", 999999)),
            len(item.get("template", "")),
        ),
    )[0]


def METAQA_SELECT_EXECUTABLE_QUERY(g_candidates: Any, g_kb: Any) -> Any:
    candidates_graph = store.get_context(g_candidates)
    kb_graph = store.get_context(g_kb)
    meta = _graph_meta(candidates_graph)
    items = _candidate_items(candidates_graph)

    for item in items:
        item["has_results"] = _has_results(kb_graph, item["template"])

    chosen = _choose_candidate(items, meta.get("question", ""), meta.get("preferred_terminal_rel", ""))
    chosen_template = chosen.get("template", "") if chosen else ""
    generated_query = _build_query_from_template(chosen_template) if chosen_template else ""

    logger.info(
        "METAQA_SELECT_EXECUTABLE_QUERY: chosen template=%s rank=%s hops=%s has_results=%s",
        chosen.get("id") if chosen else "",
        chosen.get("rank") if chosen else "",
        chosen.get("hops") if chosen else "",
        chosen.get("has_results") if chosen else False,
    )

    g_uri = _graph_uri(
        "metaqa_select_executable_query",
        [str(g_candidates), str(g_kb), chosen_template],
    )
    g = store.get_context(g_uri)
    gen = URIRef(str(g_uri) + "#query")
    g.bind("cand", CAND)

    g.add((gen, RDF.type, CAND.GeneratedQuery))
    if meta["question"]:
        g.add((gen, CAND.question, Literal(meta["question"])))
    if meta["anchor"]:
        g.add((gen, CAND.anchor, Literal(meta["anchor"])))
    if meta["entity"]:
        g.add((gen, CAND.entity, URIRef(meta["entity"])))
    g.add((gen, CAND.sparql, Literal(generated_query)))

    if chosen:
        g.add((gen, CAND.templateId, Literal(chosen["id"])))
        g.add((gen, CAND.rank, Literal(int(chosen["rank"]))))
        g.add((gen, CAND.depth, Literal(int(chosen["hops"]))))
        g.add((gen, CAND.reason, Literal(chosen.get("path", ""))))
        g.add((gen, CAND.viaProperty, Literal(chosen.get("terminal_rel", ""))))
        g.add((gen, CAND.pathRels, Literal("|".join(chosen.get("path_rels", [])))))
        g.add((gen, CAND.mentionText, Literal(chosen_template)))
        g.add((gen, CAND.hasResult, Literal(bool(chosen.get("has_results")), datatype=XSD.boolean)))

    for item in items:
        node = URIRef(str(g_uri) + "#" + item["id"])
        g.add((node, RDF.type, CAND.BeamNode))
        g.add((node, CAND.templateId, Literal(item["id"])))
        g.add((node, CAND.rank, Literal(int(item["rank"]))))
        g.add((node, CAND.depth, Literal(int(item["hops"]))))
        g.add((node, CAND.reason, Literal(item.get("path", ""))))
        g.add((node, CAND.viaProperty, Literal(item.get("terminal_rel", ""))))
        g.add((node, CAND.pathRels, Literal("|".join(item.get("path_rels", [])))))
        g.add((node, CAND.mentionText, Literal(item["template"])))
        g.add((node, CAND.hasResult, Literal(bool(item.get("has_results")), datatype=XSD.boolean)))
        g.add((gen, CAND.candidate, node))

    return g_uri