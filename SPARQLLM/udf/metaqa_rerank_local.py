from __future__ import annotations

import hashlib
from typing import Any

from rdflib import BNode, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from rdflib.plugins.sparql import prepareQuery

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.metaqa_anchor_rerank import rerank_candidates_local
from SPARQLLM.udf.SPARQLLM import store


SCHEMA = Namespace("https://schema.org/")
CAND = Namespace("http://example.org/cand#")


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:metaqa-rerank:{prefix}:{digest}")


def _extract_candidates(g_search: Any) -> list[dict[str, Any]]:
    named_graph = store.get_context(g_search)
    query = prepareQuery(
        """
        PREFIX schema: <https://schema.org/>
        PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX cand:   <http://example.org/cand#>

        SELECT ?pos ?entity ?label ?desc ?score
        WHERE {
          ?item a schema:DataFeedItem ;
                schema:position ?pos ;
                schema:item ?entity .
          OPTIONAL { ?entity rdfs:label ?label }
          OPTIONAL { ?entity schema:description ?desc }
          OPTIONAL { ?item cand:searchScore ?score }
        }
        ORDER BY ?pos
        """
    )
    rows = named_graph.query(query)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "rank": int(str(row.pos)),
                "originalPosition": int(str(row.pos)),
                "entity": str(row.entity),
                "label": str(row.label) if row.label is not None else "",
                "description": str(row.desc) if row.desc is not None else "",
                "score": float(str(row.score)) if row.score is not None else 0.0,
            }
        )
    return out


def METAQA_RERANK_LOCAL(*args: Any) -> Any:
    """Rerank MetaQA anchor candidates with a local LLM.

    Supported signatures:
      - ggf:METAQA-RERANK-LOCAL(question_text, g_search)
    """
    if len(args) != 2:
        raise ValueError("METAQA-RERANK-LOCAL expects (question_text, g_search)")

    question_text = _to_text(args[0])
    g_search = args[1]
    candidates = _extract_candidates(g_search)

    cfg = ConfigSingleton().config
    provider = cfg["Requests"].get("SLM-RERANK-BACKEND", "ollama").strip().lower()
    api_url = cfg["Requests"].get("SLM-OLLAMA-URL", "http://localhost:11434/api/generate").strip()
    if provider == "groq":
        model = cfg["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile").strip()
    else:
        model = cfg["Requests"].get("SLM-OLLAMA-MODEL", "llama3.1:latest").strip()
    timeout = int(cfg["Requests"].get("SLM-TIMEOUT", 120))

    ranked, stats = rerank_candidates_local(
        question_text=question_text,
        candidates=candidates,
        provider=provider,
        api_url=api_url,
        model=model,
        timeout=timeout,
    )

    out_uri = _graph_uri("rerank", [question_text, str(g_search)])
    out = store.get_context(out_uri)
    out.bind("cand", CAND)
    out.bind("schema", SCHEMA)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, CAND.RerankResult))
    out.add((root, SCHEMA.query, Literal(question_text)))
    out.add((root, CAND.sourceGraph, URIRef(str(g_search))))
    out.add((root, CAND.requestBytes, Literal(int(stats["request_bytes"]), datatype=XSD.integer)))
    out.add((root, CAND.responseBytes, Literal(int(stats["response_bytes"]), datatype=XSD.integer)))
    out.add((root, CAND.usedFallback, Literal(bool(stats["used_fallback"]), datatype=XSD.boolean)))

    for row in ranked:
        node = BNode()
        out.add((node, RDF.type, CAND.RerankedEntity))
        out.add((node, CAND.entity, URIRef(row["entity"])))
        out.add((node, CAND.label, Literal(str(row.get("label", "")))))
        out.add((node, CAND.rank, Literal(int(row["rank"]), datatype=XSD.integer)))
        out.add((node, CAND.originalPosition, Literal(int(row.get("originalPosition", 0)), datatype=XSD.integer)))
        out.add((node, CAND.searchScore, Literal(float(row.get("score", 0.0)), datatype=XSD.float)))
        out.add((node, CAND.confidence, Literal(float(row.get("confidence", 0.0)), datatype=XSD.float)))
        out.add((node, CAND.reason, Literal(str(row.get("reason", "")))))
        out.add((root, CAND.candidate, node))

    return out_uri
