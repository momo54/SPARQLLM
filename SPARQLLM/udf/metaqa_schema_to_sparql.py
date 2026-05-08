import hashlib
import logging
import os
import re
from typing import Any

from groq import Groq
from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import RDF
from rdflib.plugins.sparql.parser import parseQuery

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.SPARQLLM import store

logger = logging.getLogger(__name__)

CAND = Namespace("http://example.org/cand#")
M = Namespace("http://metaqa.org/schema/")


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    key = "|".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:beam:{prefix}:{digest}")


# ---------------------------------------------------------------------------
# Helpers to walk the beam graph
# ---------------------------------------------------------------------------

def _node_attr(graph, node, predicate, default="") -> str:
    for _, _, obj in graph.triples((node, predicate, None)):
        return str(obj)
    return default


def _root_entity(graph) -> str:
    for node, _, depth in graph.triples((None, CAND.depth, None)):
        if str(depth).strip() == "0":
            ent = _node_attr(graph, node, CAND.entity)
            if ent:
                return ent
    return ""


def _leaf_nodes(graph) -> list[dict]:
    leaves = []
    for node, _, is_leaf in graph.triples((None, CAND.isLeaf, None)):
        if str(is_leaf).strip().lower() != "true":
            continue
        try:
            rank = int(_node_attr(graph, node, CAND.rank, "999999"))
        except ValueError:
            rank = 999999
        leaves.append({
            "node": node,
            "rank": rank,
            "label": _node_attr(graph, node, CAND.label),
            "entity": _node_attr(graph, node, CAND.entity),
            "parent": next((p for _, _, p in graph.triples((node, CAND.parent, None))), None),
            "via_direction": _node_attr(graph, node, CAND.viaDirection),
            "via_property": _node_attr(graph, node, CAND.viaProperty),
        })
    leaves.sort(key=lambda x: x["rank"])
    return leaves


def _schema_path_nodes(graph) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for node in graph.subjects(RDF.type, CAND.SchemaPath):
        try:
            rank = int(_node_attr(graph, node, CAND.rank, "999999"))
        except ValueError:
            rank = 999999
        try:
            depth = int(_node_attr(graph, node, CAND.hopCount, _node_attr(graph, node, CAND.depth, "0")))
        except ValueError:
            depth = 0
        paths.append(
            {
                "node": node,
                "rank": rank,
                "depth": depth,
                "label": _node_attr(graph, node, CAND.label),
                "parent": next((p for _, _, p in graph.triples((node, CAND.parent, None))), None),
                "via_direction": _node_attr(graph, node, CAND.viaDirection),
                "via_property": _node_attr(graph, node, CAND.viaProperty),
            }
        )
    paths.sort(key=lambda x: (x["depth"], x["rank"]))
    return paths


def _path_edges(graph, leaf: dict) -> list[dict]:
    """Return ordered list of edges from root to leaf."""
    edges = []
    cur = leaf
    parent = leaf.get("parent")
    while parent is not None:
        parent_entity = _node_attr(graph, parent, CAND.entity)
        prop = cur.get("via_property") or ""
        direction = cur.get("via_direction") or "out"
        rel = prop.rsplit("/", 1)[-1] if prop else "?"
        edges.append({
            "parent_entity": parent_entity,
            "child_entity": str(cur.get("entity") or ""),
            "prop": prop,
            "rel": rel,
            "direction": direction,
        })
        cur = {
            "entity": parent_entity,
            "via_direction": _node_attr(graph, parent, CAND.viaDirection),
            "via_property": _node_attr(graph, parent, CAND.viaProperty),
        }
        parent = next((p for _, _, p in graph.triples((parent, CAND.parent, None))), None)
    edges.reverse()
    return edges


def _path_str(edges: list[dict]) -> str:
    """Human-readable path like: in:starred_actors -> out:directed_by"""
    return " -> ".join(f"{e['direction']}:{e['rel']}" for e in edges)


# ---------------------------------------------------------------------------
# Path selection + deterministic query building
# ---------------------------------------------------------------------------

def _groq_choose_path(
    question: str,
    anchor: str,
    root_iri: str,
    depth: int,
    candidates: list[dict[str, Any]],
) -> int | None:
    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")
    client = Groq(api_key=api_key, max_retries=0)

    candidate_lines = "\n".join(
        f"{item['id']}. {item['path']}" for item in candidates
    ) or "(none)"

    prompt = f"""You are selecting a MetaQA schema path.

Direction conventions are STRICT and mandatory:
  in:PROP  => previous node is OBJECT, new variable is SUBJECT.
              Triple pattern: ?new mrel:PROP ?prev .
  out:PROP => previous node is SUBJECT, new variable is OBJECT.
              Triple pattern: ?prev mrel:PROP ?new .

Worked examples:
  Path: in:directed_by -> out:in_language
    ?v1 mrel:directed_by <ANCHOR> .
    ?v1 mrel:in_language ?answer .

  Path: in:starred_actors -> out:directed_by
    ?v1 mrel:starred_actors <ANCHOR> .
    ?v1 mrel:directed_by ?answer .

Question: {question}
Anchor label: {anchor}
Anchor entity IRI: <{root_iri}>

Candidate paths with exactly {depth} hop(s):
{candidate_lines}

Task:
- Decide whether one of these paths is sufficient to answer the question.
- If yes, choose exactly one path id from the list.
- If none of these paths can answer the question, return NONE.
- Prefer the most semantically precise path for the asked answer type.
- Do not write SPARQL.

Return exactly one token:
- the integer path id, for example 2
- or NONE"""

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=32,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if raw.upper() == "NONE":
            return None
        match = re.search(r"\b(\d+)\b", raw)
        if not match:
            return None
        choice = int(match.group(1))
        if 1 <= choice <= len(candidates):
            return choice
        return None
    except Exception as exc:
        logger.warning("METAQA_SCHEMA_TO_SPARQL path selection failed: %s", exc)
        return None


def _dedupe_paths_by_depth(graph, leaves: list[dict], max_paths_per_depth: int = 8) -> dict[int, list[dict[str, Any]]]:
    by_depth: dict[int, list[dict[str, Any]]] = {}
    seen: dict[int, set[tuple[tuple[str, str], ...]]] = {}

    for leaf in leaves:
        edges = _path_edges(graph, leaf)
        if not edges:
            continue
        depth = len(edges)
        key = tuple((edge["direction"], edge["rel"]) for edge in edges)
        if key in seen.setdefault(depth, set()):
            continue
        seen[depth].add(key)
        items = by_depth.setdefault(depth, [])
        if len(items) >= max_paths_per_depth:
            continue
        items.append(
            {
                "id": len(items) + 1,
                "rank": int(leaf.get("rank", 999999)),
                "path": _path_str(edges),
                "edges": edges,
            }
        )

    return by_depth


def _collect_paths_by_depth(graph, max_paths_per_depth: int = 8) -> dict[int, list[dict[str, Any]]]:
    schema_nodes = _schema_path_nodes(graph)
    if schema_nodes:
        return _dedupe_paths_by_depth(graph, schema_nodes, max_paths_per_depth=max_paths_per_depth)
    return _dedupe_paths_by_depth(graph, _leaf_nodes(graph), max_paths_per_depth=max_paths_per_depth)


def _infer_answer_type(question: str) -> str:
    q = question.lower()
    if "language" in q or "languages" in q or "spoken" in q:
        return "language"
    if "release date" in q or "release dates" in q or "release year" in q or "released in" in q or "what year" in q or "when" in q:
        return "year"
    if "genre" in q or "genres" in q or "type of" in q:
        return "genre"
    if "tag" in q or "tags" in q:
        return "tag"
    if "which films" in q or "which film" in q or "which movies" in q or "which movie" in q:
        return "movie"
    if q.startswith("who ") or " who " in q:
        return "person"
    return "unknown"


def _terminal_type(edges: list[dict[str, str]]) -> str:
    if not edges:
        return "unknown"
    rel = edges[-1]["rel"]
    direction = edges[-1]["direction"]
    mapping = {
        ("directed_by", "in"): "movie",
        ("directed_by", "out"): "person",
        ("written_by", "in"): "movie",
        ("written_by", "out"): "person",
        ("starred_actors", "in"): "movie",
        ("starred_actors", "out"): "person",
        ("in_language", "in"): "movie",
        ("in_language", "out"): "language",
        ("release_year", "in"): "movie",
        ("release_year", "out"): "year",
        ("has_genre", "in"): "movie",
        ("has_genre", "out"): "genre",
        ("has_tags", "in"): "movie",
        ("has_tags", "out"): "tag",
    }
    return mapping.get((rel, direction), "unknown")


def _build_query_from_edges(root_iri: str, edges: list[dict[str, str]]) -> str:
    if not root_iri or not edges:
        return ""

    lines = [
        "PREFIX mrel: <http://metaqa.org/relation/>",
        "SELECT ?answer",
        "WHERE {",
    ]
    prev_term = f"<{root_iri}>"
    for idx, edge in enumerate(edges, start=1):
        next_term = "?answer" if idx == len(edges) else f"?v{idx}"
        pred = f"mrel:{edge['rel']}"
        if edge["direction"] == "out":
            lines.append(f"  {prev_term} {pred} {next_term} .")
        else:
            lines.append(f"  {next_term} {pred} {prev_term} .")
        prev_term = next_term
    lines.append(f"  FILTER (?answer != <{root_iri}>)")
    lines.append("}")
    return "\n".join(lines)


def _question_relation_hints(question: str) -> set[str]:
    q = question.lower()
    hints = set()
    mapping = {
        "written_by": ["written", "screenwriter", "wrote", "writer"],
        "directed_by": ["directed", "director"],
        "starred_actors": ["actor", "actors", "starred", "co-star", "acted"],
        "in_language": ["language", "languages", "spoken"],
        "release_year": ["year", "years", "release", "released", "date"],
        "has_genre": ["genre", "genres", "type", "types"],
    }
    for rel, kws in mapping.items():
        if any(k in q for k in kws):
            hints.add(rel)
    return hints


def _path_heuristic_score(question: str, item: dict[str, Any]) -> tuple[int, int, int, int]:
    hints = _question_relation_hints(question)
    rels = [edge["rel"] for edge in item.get("edges", [])]
    terminal = rels[-1] if rels else ""
    hint_hits = sum(1 for rel in rels if rel in hints)
    covers_all = 1 if hints and hints.issubset(set(rels)) else 0
    terminal_match = 1 if terminal in hints else 0
    return (covers_all, hint_hits, terminal_match, -int(item.get("rank", 999999)))


def _parse_status(query_text: str) -> tuple[bool, str]:
    if not query_text.strip():
        return False, "empty"
    try:
        parseQuery(query_text)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _execute_status(query_text: str, g_kb: Any = None) -> tuple[bool, int, str]:
    if not query_text.strip():
        return False, 0, "not-run"

    try:
        if g_kb is not None and str(g_kb).strip():
            kb_graph = store.get_context(URIRef(str(g_kb)))
            res = kb_graph.query(query_text)
        else:
            res = store.query(query_text)

        count = 0
        for _ in res:
            count += 1
            if count > 0:
                break
        return count > 0, count, "nonempty" if count > 0 else "empty"
    except Exception as exc:
        return False, 0, str(exc)


def _select_valid_path_progressively(
    question: str,
    anchor: str,
    root_iri: str,
    paths_by_depth: dict[int, list[dict[str, Any]]],
    g_kb: Any = None,
) -> tuple[dict[str, Any] | None, int | None, str, str, int]:
    answer_type = _infer_answer_type(question)
    last_parse_status = "not-run"
    last_exec_status = "not-run"
    last_result_count = 0

    for depth in sorted(paths_by_depth):
        raw_candidates = paths_by_depth[depth]
        if not raw_candidates:
            continue
        if answer_type == "unknown":
            candidates = list(raw_candidates)
        else:
            candidates = [
                item for item in raw_candidates
                if _terminal_type(item["edges"]) == answer_type
            ]
            if not candidates:
                logger.info(
                    "METAQA_SCHEMA_TO_SPARQL: skipping depth=%d, no candidate with answer_type=%s",
                    depth,
                    answer_type,
                )
                continue

        candidates.sort(key=lambda item: _path_heuristic_score(question, item), reverse=True)

        # Minimal retry policy: at most 2 attempts per depth.
        attempts = 0
        remaining = list(candidates)
        while remaining and attempts < 2:
            attempts += 1
            choice = _groq_choose_path(question, anchor, root_iri, depth, remaining)
            selected = next((item for item in remaining if item["id"] == choice), None) if choice is not None else None
            if selected is None:
                selected = remaining[0]

            generated_query = _build_query_from_edges(root_iri, selected["edges"])
            parse_ok, parse_status = _parse_status(generated_query)
            last_parse_status = parse_status
            if not parse_ok:
                logger.info(
                    "METAQA_SCHEMA_TO_SPARQL: parse failed at depth=%d path=%s error=%s",
                    depth,
                    selected["path"],
                    parse_status,
                )
                remaining = [item for item in remaining if item["id"] != selected["id"]]
                last_exec_status = "not-run"
                last_result_count = 0
                continue

            exec_ok, result_count, exec_status = _execute_status(generated_query, g_kb=g_kb)
            last_exec_status = exec_status
            last_result_count = result_count
            if exec_ok:
                logger.info(
                    "METAQA_SCHEMA_TO_SPARQL: selected valid depth=%d path=%s",
                    depth,
                    selected["path"],
                )
                return selected, depth, last_parse_status, last_exec_status, last_result_count

            logger.info(
                "METAQA_SCHEMA_TO_SPARQL: candidate failed at depth=%d path=%s exec=%s",
                depth,
                selected["path"],
                exec_status,
            )
            remaining = [item for item in remaining if item["id"] != selected["id"]]

    return None, None, last_parse_status, last_exec_status, last_result_count


def _select_path_progressively(
    question: str,
    anchor: str,
    root_iri: str,
    paths_by_depth: dict[int, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, int | None]:
    answer_type = _infer_answer_type(question)
    for depth in sorted(paths_by_depth):
        raw_candidates = paths_by_depth[depth]
        if not raw_candidates:
            continue
        if answer_type == "unknown":
            candidates = raw_candidates
        else:
            candidates = [
                item for item in raw_candidates
            if answer_type == "unknown" or _terminal_type(item["edges"]) == answer_type
            ]
            if not candidates:
                logger.info(
                    "METAQA_SCHEMA_TO_SPARQL: skipping depth=%d, no candidate with answer_type=%s",
                    depth,
                    answer_type,
                )
                continue
        choice = _groq_choose_path(question, anchor, root_iri, depth, candidates)
        if choice is None:
            logger.info("METAQA_SCHEMA_TO_SPARQL: no path selected at depth=%d", depth)
            continue
        selected = next((item for item in candidates if item["id"] == choice), None)
        if selected is not None:
            logger.info(
                "METAQA_SCHEMA_TO_SPARQL: selected depth=%d path=%s",
                depth,
                selected["path"],
            )
            return selected, depth
    return None, None


# ---------------------------------------------------------------------------
# Public UDF
# ---------------------------------------------------------------------------

def METAQA_SCHEMA_TO_SPARQL(utterance: Any, anchor: Any, g_schema: Any, g_kb: Any = None) -> Any:
    """Generate a MetaQA SPARQL query from a DFS/beam schema graph.

    Steps:
    1. Walk the schema graph to extract unique relation paths grouped by depth.
    2. Rerank/select paths progressively by depth.
    3. Build the SPARQL query deterministically from the chosen path.
    4. Store the generated query in a new named graph and return its URI.
    """
    text_utterance = str(utterance)
    anchor_text = str(anchor)
    named_graph = store.get_context(g_schema)

    logger.info(
        "METAQA_SCHEMA_TO_SPARQL: utterance=%s anchor=%s schema_graph=%s triples=%d",
        text_utterance, anchor_text, g_schema, len(named_graph),
    )

    root_entity = _root_entity(named_graph)
    paths_by_depth = _collect_paths_by_depth(named_graph)
    selected_path, selected_depth, parse_status, exec_status, result_count = _select_valid_path_progressively(
        text_utterance,
        anchor_text,
        root_entity,
        paths_by_depth,
        g_kb=g_kb,
    )
    generated_query = _build_query_from_edges(root_entity, selected_path["edges"]) if selected_path else ""

    logger.info("METAQA_SCHEMA_TO_SPARQL: generated %d chars", len(generated_query))

    g_uri = _graph_uri("metaqa_schema_to_sparql", [text_utterance, anchor_text, str(g_schema)])
    g = store.get_context(g_uri)
    gen = URIRef(str(g_uri) + "#query")
    g.bind("cand", CAND)
    g.bind("m", M)

    g.add((gen, RDF.type, CAND.GeneratedQuery))
    g.add((gen, CAND.question, Literal(text_utterance)))
    g.add((gen, CAND.anchor, Literal(anchor_text)))
    if root_entity:
        g.add((gen, CAND.entity, URIRef(root_entity)))
    g.add((gen, CAND.sparql, Literal(generated_query)))
    g.add((gen, CAND.parseStatus, Literal(parse_status)))
    g.add((gen, CAND.execStatus, Literal(exec_status)))
    g.add((gen, CAND.resultCount, Literal(int(result_count))))
    if selected_path is not None:
        g.add((gen, CAND.reason, Literal(selected_path["path"])))
        g.add((gen, CAND.rank, Literal(int(selected_path["rank"]))))
    if selected_depth is not None:
        g.add((gen, CAND.depth, Literal(int(selected_depth))))

    return g_uri
