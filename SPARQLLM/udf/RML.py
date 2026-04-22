from __future__ import annotations

import logging
import sys
import tempfile
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from contextlib import contextmanager

from rdflib import URIRef

from SPARQLLM.udf.SPARQLLM import store


logger = logging.getLogger(__name__)
INLINE_JSON_SOURCE = "urn:slm:inline-json"


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _as_path(value: object) -> Path:
    """Convert file path literals/URIs used in SPARQL bindings to a local Path."""
    text = str(value)
    parsed = urlparse(text)
    if parsed.scheme == "file":
        return Path(parsed.path)
    return Path(text)


def _ensure_fog_rml_importable() -> None:
    """Try local sibling checkout fallback when fog_rml is not installed in env."""
    try:
        import fog_rml  # noqa: F401
        return
    except Exception:
        pass

    # Workspace layout fallback: <root>/SPARQLLM/SPARQLLM/udf/RML.py and <root>/fog-rml/src
    local_candidate = Path(__file__).resolve().parents[3] / "fog-rml" / "src"
    if local_candidate.exists():
        candidate_text = str(local_candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)


def _looks_like_uri_or_abs_path(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https", "file", "urn"}:
        return True
    return Path(value).is_absolute()


def _override_rml_sources(mapping_text: str, data_folder: str | None, data_files: list[str]) -> str:
    pattern = re.compile(r'(\brml:source\s+)"([^"]+)"')
    index_ref = {"i": 0}

    def repl(match):
        prefix, source_value = match.group(1), match.group(2)

        if source_value == INLINE_JSON_SOURCE:
            return match.group(0)

        if data_files:
            if len(data_files) == 1:
                replacement = data_files[0]
            else:
                pos = index_ref["i"]
                replacement = data_files[pos] if pos < len(data_files) else source_value
            index_ref["i"] += 1
            return f'{prefix}"{Path(replacement).resolve().as_posix()}"'

        if data_folder and not _looks_like_uri_or_abs_path(source_value):
            replacement = (Path(data_folder).resolve() / source_value).resolve()
            return f'{prefix}"{replacement.as_posix()}"'

        return match.group(0)

    return pattern.sub(repl, mapping_text)


def rml(json_string: object, rml_file: object):
    """ggf:RML(jsonString, rmlFile) -> named graph URI.

    - jsonString: raw JSON payload as a string.
    - rmlFile: path to an RML mapping file. The mapping should reference
      source `urn:slm:inline-json` that will be replaced at runtime.
    """
    try:
        _ensure_fog_rml_importable()

        from fog_rml.mapping.MappingParser import MappingParser
        from fog_rml.utils.term_utils import term_to_rdflib

        mapping_override = os.getenv("SPARQLLM_RML_MAPPING")
        mapping_path = _as_path(mapping_override if mapping_override else rml_file).resolve()
        if not mapping_path.exists():
            logger.error("RML UDF: mapping file not found: %s", mapping_path)
            return None

        json_payload = str(json_string)
        graph_uri = URIRef(f"urn:ggf:rml:{uuid4()}")
        named_graph = store.get_context(graph_uri)

        def _materialize_from_mapping(mapping_file: Path) -> int:
            parser = MappingParser(str(mapping_file))
            pipeline = parser.parse()

            triple_count = 0
            for row in pipeline.execute():
                subject = term_to_rdflib(row.get("subject"))
                predicate = term_to_rdflib(row.get("predicate"))
                obj = term_to_rdflib(row.get("object"))
                if subject is None or predicate is None or obj is None:
                    continue
                named_graph.add((subject, predicate, obj))
                triple_count += 1
            return triple_count

        mapping_text = mapping_path.read_text(encoding="utf-8")
        original_mapping_text = mapping_text

        data_folder_override = os.getenv("SPARQLLM_RML_DATA_FOLDER")
        data_files_override = os.getenv("SPARQLLM_RML_DATA_FILES", "")
        data_files = [p for p in data_files_override.split(os.pathsep) if p]

        if data_folder_override or data_files:
            mapping_text = _override_rml_sources(mapping_text, data_folder_override, data_files)

        # File-based mapping mode: keep original mapping location so relative sources resolve.
        if INLINE_JSON_SOURCE not in mapping_text and mapping_text == original_mapping_text:
            with _pushd(mapping_path.parent):
                triple_count = _materialize_from_mapping(mapping_path)

            logger.info(
                "RML UDF: materialized %d triples into graph %s using %s",
                triple_count,
                graph_uri,
                mapping_path,
            )
            return graph_uri

        with tempfile.TemporaryDirectory(prefix="sparqllm_rml_") as temp_dir:
            temp_dir_path = Path(temp_dir)
            updated_mapping_text = mapping_text
            if INLINE_JSON_SOURCE in updated_mapping_text:
                inline_json_path = temp_dir_path / "inline.json"
                inline_json_path.write_text(json_payload, encoding="utf-8")
                updated_mapping_text = updated_mapping_text.replace(
                    INLINE_JSON_SOURCE,
                    inline_json_path.as_posix(),
                )

            runtime_mapping_path = temp_dir_path / "runtime_mapping.ttl"
            runtime_mapping_path.write_text(updated_mapping_text, encoding="utf-8")

            triple_count = _materialize_from_mapping(runtime_mapping_path)

            logger.info(
                "RML UDF: materialized %d triples into graph %s using %s",
                triple_count,
                graph_uri,
                mapping_path,
            )

        return graph_uri
    except Exception as exc:
        logger.exception("RML UDF failed: %s", exc)
        return None
