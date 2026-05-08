from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from SPARQLLM.metaqa_anchor_faiss import search_anchor_faiss
from SPARQLLM.udf.SPARQLLM import store


SCHEMA = Namespace("https://schema.org/")
CAND = Namespace("http://example.org/cand#")


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:metaqa-faiss:{prefix}:{digest}")


def _default_index_dir() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return str((repo_root / "xp-ggf-script" / "data" / "metaqa_anchor_faiss").resolve())


def METAQA_SEARCH_FAISS(*args: Any) -> Any:
    """Search the persistent MetaQA FAISS anchor index.

    Supported signatures:
      - ggf:METAQA-SEARCH-FAISS(query)
      - ggf:METAQA-SEARCH-FAISS(query, top_k)
      - ggf:METAQA-SEARCH-FAISS(query, top_k, index_dir)
    """
    if not 1 <= len(args) <= 3:
        raise ValueError("METAQA-SEARCH-FAISS expects (query[, top_k[, index_dir]])")

    query = _to_text(args[0])
    top_k = max(1, _to_int(args[1], 10)) if len(args) >= 2 else 10
    index_dir = _to_text(args[2]) if len(args) >= 3 else _default_index_dir()
    index_dir = index_dir or _default_index_dir()

    results = search_anchor_faiss(
        query=query,
        index_dir=index_dir,
        top_k=top_k,
        embedding_model="nomic-embed-text",
    )

    out_uri = _graph_uri("search", [query, str(top_k), str(index_dir)])
    out = store.get_context(out_uri)
    out.bind("schema", SCHEMA)
    out.bind("cand", CAND)

    root = URIRef(str(out_uri) + "#root")
    out.add((root, RDF.type, SCHEMA.DataFeed))
    out.add((root, SCHEMA.query, Literal(query)))
    out.add((root, CAND.indexDir, Literal(index_dir)))

    for row in results:
        item = URIRef(str(out_uri) + f"#item-{row['rank']}")
        entity = URIRef(str(row["entity"]))
        out.add((root, SCHEMA.dataFeedElement, item))
        out.add((item, RDF.type, SCHEMA.DataFeedItem))
        out.add((item, SCHEMA.position, Literal(int(row["rank"]), datatype=XSD.integer)))
        out.add((item, SCHEMA.item, entity))
        out.add((item, CAND.searchScore, Literal(float(row["score"]), datatype=XSD.float)))
        out.add((entity, RDFS.label, Literal(str(row.get("label", "")))))
        out.add((entity, SCHEMA.description, Literal(str(row.get("text", "")))))
        out.add((entity, CAND.sourceQuestionCount, Literal(int(row.get("source_question_count", 0)), datatype=XSD.integer)))

    return out_uri
