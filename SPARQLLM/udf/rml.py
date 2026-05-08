from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef

from SPARQLLM.udf.SPARQLLM import store


logger = logging.getLogger(__name__)

INLINE_JSON_MARKER = "urn:slm:inline-json"


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _graph_uri(parts: list[str]) -> URIRef:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:rml:{digest}")


def _ensure_pyhartig():
    try:
        from pyhartig.mapping.MappingParser import MappingParser
    except ImportError as exc:
        raise RuntimeError(
            "ggf:RML requires the optional dependency 'pyhartig'. Install it with 'pip install pyhartig'."
        ) from exc
    return MappingParser


def _coerce_json_payload(payload: str) -> str:
    if not payload:
        raise ValueError("ggf:RML expects a non-empty JSON string as its first argument.")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ggf:RML received invalid JSON: {exc}") from exc
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _copy_mapping_tree(mapping_path: Path, temp_dir: Path) -> Path:
    copied_mapping = temp_dir / mapping_path.name
    copied_mapping.write_text(mapping_path.read_text(encoding="utf-8"), encoding="utf-8")
    return copied_mapping


def _rewrite_mapping_for_inline_json(mapping_text: str, inline_json_name: str) -> str:
    updated = mapping_text.replace(f'"{INLINE_JSON_MARKER}"', f'"{inline_json_name}"')
    updated = updated.replace(f"<{INLINE_JSON_MARKER}>", f'"{inline_json_name}"')
    return updated


def _mapping_uses_inline_marker(mapping_text: str) -> bool:
    return INLINE_JSON_MARKER in mapping_text


def _row_to_rdflib_term(term: Any):
    module_name = term.__class__.__module__
    if not module_name.startswith("pyhartig."):
        return term

    from rdflib import BNode, Literal

    kind = term.__class__.__name__
    if kind == "IRI":
        return URIRef(term.value)
    if kind == "BlankNode":
        return BNode(term.identifier)
    if kind == "Literal":
        language = getattr(term, "language", None)
        datatype = getattr(term, "datatype_iri", None)
        if language:
            return Literal(term.lexical_form, lang=language)
        if datatype:
            return Literal(term.lexical_form, datatype=URIRef(datatype))
        return Literal(term.lexical_form)
    return term


def _materialize_pipeline_results(results: Any, out_graph: Graph) -> None:
    for row in results:
        subject = _row_to_rdflib_term(row.get("subject"))
        predicate = _row_to_rdflib_term(row.get("predicate"))
        obj = _row_to_rdflib_term(row.get("object"))
        if subject is None or predicate is None or obj is None:
            continue
        out_graph.add((subject, predicate, obj))


def RML(*args: Any) -> Any:
    """Run an RML mapping with inline JSON content via pyhartig and return a named graph.

    Supported signatures:
      - ggf:RML(json_string, rml_file)
      - ggf:RML(json_string, rml_file, graph_uri)

    The mapping can use the placeholder source `urn:slm:inline-json`, which will be
    replaced at runtime by a temporary JSON file built from `json_string`.
    As a convenience for simple demos, if the marker is absent and the mapping has
    exactly one JSON logical source, you can point that source directly to
    `inline.json`; the temp workspace will provide that file too.
    """
    if not 2 <= len(args) <= 3:
        raise ValueError("RML expects (json_string, rml_file[, graph_uri]).")

    json_payload = _coerce_json_payload(_to_text(args[0]))
    mapping_path = Path(_to_text(args[1])).expanduser().resolve()
    graph_text = _to_text(args[2]) if len(args) >= 3 else ""

    if not mapping_path.exists():
        raise FileNotFoundError(f"RML mapping file not found: {mapping_path}")

    MappingParser = _ensure_pyhartig()
    out_uri = URIRef(graph_text) if graph_text else _graph_uri([json_payload, str(mapping_path)])
    out_graph = store.get_context(out_uri)

    with tempfile.TemporaryDirectory(prefix="sparqllm-rml-") as tmp:
        temp_dir = Path(tmp)
        inline_json_path = temp_dir / "inline.json"
        inline_json_path.write_text(json_payload, encoding="utf-8")

        copied_mapping = _copy_mapping_tree(mapping_path, temp_dir)
        mapping_text = copied_mapping.read_text(encoding="utf-8")
        if _mapping_uses_inline_marker(mapping_text):
            mapping_text = _rewrite_mapping_for_inline_json(mapping_text, inline_json_path.name)
            copied_mapping.write_text(mapping_text, encoding="utf-8")

        for item in mapping_path.parent.iterdir():
            if item == mapping_path:
                continue
            destination = temp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            elif not destination.exists():
                shutil.copy2(item, destination)

        parser = MappingParser(str(copied_mapping))
        pipeline = parser.parse()
        _materialize_pipeline_results(pipeline.execute(), out_graph)

    logger.info("RML: materialized %s triples into %s from %s", len(out_graph), out_uri, mapping_path)
    return out_uri
