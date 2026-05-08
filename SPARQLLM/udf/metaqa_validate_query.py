import hashlib
import logging
from typing import Any

from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.udf.SPARQLLM import store

logger = logging.getLogger(__name__)

CAND = Namespace("http://example.org/cand#")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    key = "|".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:beam:{prefix}:{digest}")


def _literal_str(graph, subject, predicate) -> str:
    for _, _, obj in graph.triples((subject, predicate, None)):
        return str(obj)
    return ""


def _normalize_answer(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def _split_gold_answers(text: str) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in str(text).split("|") if part.strip()]


def _label_in_graph(graph, entity: URIRef) -> str:
    for _, _, obj in graph.triples((entity, None, None)):
        if str(obj).strip() and str(obj) == str(obj):
            break
    for _, _, obj in graph.triples((entity, URIRef("http://metaqa.org/relation/label"), None)):
        return str(obj)
    for _, _, obj in graph.triples((entity, URIRef("http://www.w3.org/2000/01/rdf-schema#label"), None)):
        return str(obj)
    for _, _, obj in graph.triples((entity, None, None)):
        if isinstance(obj, Literal) and str(obj).strip():
            return str(obj)
    tail = str(entity).rsplit("/", 1)[-1]
    return tail.replace("_", " ")


def _term_to_answer(kb_graph, term: Any) -> str:
    if isinstance(term, URIRef):
        return _label_in_graph(kb_graph, term)
    return str(term)


def METAQA_VALIDATE_QUERY(g_query: Any, gold_answers: Any, g_kb: Any) -> Any:
    """Execute a generated MetaQA query and compare predictions to gold answers.

    Parameters
    ----------
    g_query:
        Named graph produced by METAQA_SCHEMA_TO_SPARQL.
    gold_answers:
        Pipe-separated gold answers string as used in the benchmark queries.
    g_kb:
        Named graph URI holding the local MetaQA KB.
    """
    query_graph = store.get_context(g_query)
    kb_graph = store.get_context(g_kb)

    gen = next(query_graph.subjects(RDF.type, CAND.GeneratedQuery), None)
    sparql = _literal_str(query_graph, gen, CAND.sparql) if gen is not None else ""
    parse_status = _literal_str(query_graph, gen, CAND.parseStatus) if gen is not None else ""
    exec_status = _literal_str(query_graph, gen, CAND.execStatus) if gen is not None else ""

    gold_list = _split_gold_answers(str(gold_answers))
    gold_norm = {_normalize_answer(x): x for x in gold_list}

    predicted_raw: list[str] = []
    predicted_norm: dict[str, str] = {}
    execution_error = ""

    if sparql.strip():
        try:
            for row in kb_graph.query(sparql):
                if hasattr(row, "asdict"):
                    mapping = row.asdict()
                    term = mapping.get("answer")
                    if term is None and mapping:
                        term = next(iter(mapping.values()))
                else:
                    term = row[0] if row else None
                if term is None:
                    continue
                ans = _term_to_answer(kb_graph, term)
                predicted_raw.append(ans)
                predicted_norm[_normalize_answer(ans)] = ans
        except Exception as exc:
            execution_error = str(exc)
            logger.warning("METAQA_VALIDATE_QUERY execution failed: %s", exc)

    exact_match = set(predicted_norm) == set(gold_norm)
    has_gold_hit = bool(set(predicted_norm) & set(gold_norm))
    missing = [gold_norm[k] for k in sorted(set(gold_norm) - set(predicted_norm))]
    extra = [predicted_norm[k] for k in sorted(set(predicted_norm) - set(gold_norm))]

    g_uri = _graph_uri("metaqa_validate_query", [str(g_query), str(g_kb), str(gold_answers)])
    g = store.get_context(g_uri)
    g.bind("cand", CAND)

    report = URIRef(str(g_uri) + "#report")
    g.add((report, RDF.type, CAND.QueryValidation))
    if gen is not None:
        g.add((report, CAND.sourceQueryGraph, URIRef(str(g_query))))
    g.add((report, CAND.goldAnswers, Literal(str(gold_answers))))
    g.add((report, CAND.sparql, Literal(sparql)))
    g.add((report, CAND.parseStatus, Literal(parse_status or ("ok" if sparql else "empty"))))
    g.add((report, CAND.execStatus, Literal(exec_status or ("error" if execution_error else "empty"))))
    g.add((report, CAND.resultCount, Literal(len(predicted_norm), datatype=XSD.integer)))
    g.add((report, CAND.exactMatch, Literal(bool(exact_match), datatype=XSD.boolean)))
    g.add((report, CAND.hasGoldHit, Literal(bool(has_gold_hit), datatype=XSD.boolean)))

    if execution_error:
        g.add((report, CAND.failureReason, Literal(execution_error)))

    for value in gold_list:
        g.add((report, CAND.goldAnswer, Literal(value)))
    for value in predicted_raw:
        g.add((report, CAND.predictedAnswer, Literal(value)))
    for value in missing:
        g.add((report, CAND.missingAnswer, Literal(value)))
    for value in extra:
        g.add((report, CAND.extraAnswer, Literal(value)))

    return g_uri
