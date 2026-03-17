from __future__ import annotations

import hashlib
import json as _json
import logging
import re
from typing import Any

import requests
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from SPARQLLM.udf.SPARQLLM import store

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
_WD_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "SPARQLLM/0.1 (beam-expand-related)",
}
from SPARQLLM.udf.mcp.providers.wikidata_provider import WikidataProvider

CAND = Namespace("http://example.org/cand#")
SCHEMA = Namespace("https://schema.org/")


def _to_text(term: Any) -> str:
    return "" if term is None else str(term).strip()


def _to_int(term: Any, default: int) -> int:
    try:
        return int(str(term))
    except Exception:
        return default


def _to_bool(term: Any, default: bool = False) -> bool:
    if term is None:
        return default
    s = str(term).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _graph_uri(prefix: str, parts: list[str]) -> URIRef:
    key = "|".join(parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return URIRef(f"urn:beam:{prefix}:{digest}")


def _extract_mentions(question: str, max_mentions: int = 6) -> list[str]:
    # Keep quoted spans first, then multi-word proper nouns, then single
    # title-case words, then content words.
    mentions: list[str] = []

    quoted = re.findall(r'"([^"]+)"', question)
    mentions.extend([q.strip() for q in quoted if q.strip()])

    # Multi-word proper nouns first (e.g. "Isaac Asimov")
    multi_title = re.findall(r"\b(?:[A-Z][a-zA-Z\-]{1,}\s+)+[A-Z][a-zA-Z\-]{2,}\b", question)
    mentions.extend([m.strip() for m in multi_title if m.strip()])

    # Individual title-case words
    title_like = re.findall(r"\b[A-Z][a-zA-Z\-]{2,}\b", question)
    mentions.extend([t.strip() for t in title_like if t.strip()])

    words = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{3,}\b", question)
    mentions.extend([w.strip() for w in words if w.strip()])

    # Stable unique while preserving order.
    unique: list[str] = []
    seen = set()
    for m in mentions:
        k = m.lower()
        if k not in seen:
            seen.add(k)
            unique.append(m)
        if len(unique) >= max_mentions:
            break

    if not unique and question:
        unique = [question[:80]]

    return unique


def _beam_nodes(graph: Graph) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for n in graph.subjects(RDF.type, CAND.BeamNode):
        depth = 0
        score = 0.0
        mention = ""
        entity = None
        label = None
        for _, _, d in graph.triples((n, CAND.depth, None)):
            try:
                depth = int(str(d))
            except Exception:
                depth = 0
        for _, _, s in graph.triples((n, CAND.score, None)):
            try:
                score = float(str(s))
            except Exception:
                score = 0.0
        for _, _, m in graph.triples((n, CAND.mentionText, None)):
            mention = str(m)
        for _, _, e in graph.triples((n, CAND.entity, None)):
            entity = e
            break
        for _, _, l in graph.triples((n, CAND.label, None)):
            label = str(l)
            break
        nodes.append(
            {
                "node": n,
                "depth": depth,
                "score": score,
                "mention": mention,
                "entity": entity,
                "label": label,
            }
        )

    nodes.sort(key=lambda x: x["score"], reverse=True)
    return nodes


def _new_beam_graph(g_uri: URIRef, question: str, iteration: int) -> Graph:
    g = store.get_context(g_uri)
    g.bind("cand", CAND)
    g.bind("schema", SCHEMA)

    meta = URIRef(str(g_uri) + "#meta")
    g.add((meta, RDF.type, CAND.BeamState))
    g.add((meta, CAND.question, Literal(question)))
    g.add((meta, CAND.iteration, Literal(iteration, datatype=XSD.integer)))

    return g


def _add_beam_node(
    g: Graph,
    mention: str,
    depth: int,
    score: float,
    parent: Any = None,
    entity_iri: str | None = None,
    label: str | None = None,
    reason: str | None = None,
) -> BNode:
    n = BNode()
    g.add((n, RDF.type, CAND.BeamNode))
    g.add((n, CAND.mentionText, Literal(mention)))
    g.add((n, CAND.depth, Literal(depth, datatype=XSD.integer)))
    g.add((n, CAND.score, Literal(round(score, 6), datatype=XSD.decimal)))

    if parent is not None:
        g.add((n, CAND.parent, parent))
    if entity_iri:
        g.add((n, CAND.entity, URIRef(entity_iri)))
    if label:
        g.add((n, CAND.label, Literal(label)))
    if reason:
        g.add((n, CAND.reason, Literal(reason)))

    return n


def BEAM_INIT(question: Any) -> Any:
    text = _to_text(question)
    mentions = _extract_mentions(text)

    g_uri = _graph_uri("init", [text, str(len(mentions))])
    g = _new_beam_graph(g_uri, text, iteration=0)

    # Initial beam: each mention is a hypothesis with prior score.
    for i, mention in enumerate(mentions):
        prior = 1.0 / float(i + 1)
        _add_beam_node(
            g,
            mention=mention,
            depth=0,
            score=prior,
            reason="initial_mention",
        )

    return g_uri


def BEAM_STEP(question: Any, g_beam_in: Any, beam_width: Any = 5, top_k_expand: Any = 5) -> Any:
    text = _to_text(question)
    beam_k = max(1, _to_int(beam_width, 5))
    expand_k = max(1, _to_int(top_k_expand, 5))

    g_in = store.get_context(g_beam_in)
    in_nodes = _beam_nodes(g_in)

    provider = WikidataProvider()
    expanded: list[dict[str, Any]] = []

    for node in in_nodes[:beam_k]:
        mention = node["mention"]
        parent_score = float(node["score"])
        parent_depth = int(node["depth"])

        result = provider.tool_search_entities(search=mention, language="en", limit=expand_k)
        if "error" in result:
            continue

        jsonld = result.get("jsonld", {})
        items = jsonld.get("schema:dataFeedElement", []) if isinstance(jsonld, dict) else []

        for it in items:
            item = it.get("schema:item", {}) if isinstance(it, dict) else {}
            ent = str(item.get("@id", "")).strip()
            lab_obj = item.get("rdfs:label", {}) if isinstance(item, dict) else {}
            label = lab_obj.get("@value") if isinstance(lab_obj, dict) else None

            pos = int(it.get("schema:position", 1)) if isinstance(it, dict) else 1
            rank_bonus = 1.0 / float(max(pos, 1))
            score = parent_score + rank_bonus

            expanded.append(
                {
                    "mention": mention,
                    "depth": parent_depth + 1,
                    "score": score,
                    "parent": node["node"],
                    "entity": ent,
                    "label": label or mention,
                    "reason": "wikidata_search_expand",
                }
            )

    # If expansion fails, keep previous nodes so pipeline remains stable.
    if not expanded:
        expanded = [
            {
                "mention": n["mention"],
                "depth": n["depth"],
                "score": n["score"],
                "parent": n.get("parent"),
                "entity": str(n["entity"]) if n.get("entity") else None,
                "label": n.get("label") or n["mention"],
                "reason": "carry_over",
            }
            for n in in_nodes
        ]

    expanded.sort(key=lambda x: x["score"], reverse=True)
    kept = expanded[:beam_k]

    g_uri = _graph_uri(
        "step",
        [text, str(g_beam_in), str(beam_k), str(expand_k), str(len(kept))],
    )
    g = _new_beam_graph(g_uri, text, iteration=1)

    for cand in kept:
        _add_beam_node(
            g,
            mention=cand["mention"],
            depth=int(cand["depth"]),
            score=float(cand["score"]),
            parent=cand.get("parent"),
            entity_iri=cand.get("entity"),
            label=cand.get("label"),
            reason=cand.get("reason"),
        )

    return g_uri


def BEAM_BEST(g_beam: Any, top_k: Any = 1) -> Any:
    g_in = store.get_context(g_beam)
    nodes = _beam_nodes(g_in)
    leaf_subjects = {
        s for s, _, o in g_in.triples((None, CAND.isLeaf, None)) if str(o).lower() == "true"
    }
    if leaf_subjects:
        nodes = [n for n in nodes if n.get("node") in leaf_subjects]
    keep_k = max(1, _to_int(top_k, 1))

    g_uri = _graph_uri("best", [str(g_beam), str(len(nodes)), str(keep_k)])
    g = _new_beam_graph(g_uri, question="", iteration=0)

    if not nodes:
        return g_uri

    for rank, cand in enumerate(nodes[:keep_k], start=1):
        n = _add_beam_node(
            g,
            mention=cand["mention"],
            depth=int(cand["depth"]),
            score=float(cand["score"]),
            parent=cand.get("node"),
            entity_iri=str(cand["entity"]) if cand.get("entity") else None,
            label=cand.get("label"),
            reason="best_topk",
        )
        g.add((n, CAND.rank, Literal(rank, datatype=XSD.integer)))
        if rank == 1:
            g.add((n, CAND.isBest, Literal(True, datatype=XSD.boolean)))

    return g_uri


def BEAM_EXPAND_RELATED(entity_iri: Any, question: Any, limit: Any = 10) -> Any:
    """Find entities similar to *entity_iri* via Wikidata SPARQL.

    Finds other humans sharing at least one genre (P136) and the same
    occupation category (P106) as the anchor entity.  Uses a simple
    join—no UNION—to stay within Wikidata's timeout budget.

    Parameters
    ----------
    entity_iri: URIRef or str — anchor Wikidata entity (e.g. Q34981)
    question:   original question string (stored as metadata)
    limit:      maximum number of similar entities to return
    """
    iri_str = _to_text(entity_iri)
    text = _to_text(question)
    max_k = max(1, _to_int(limit, 10))

    # Normalise to full IRI
    if iri_str.startswith("Q"):
        iri_str = f"http://www.wikidata.org/entity/{iri_str}"

    sparql = f"""
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?similar ?similar_label WHERE {{
  # Anchor shares genre (P136) with candidates
  <{iri_str}> wdt:P136 ?genre .
  ?similar wdt:P136 ?genre ;
           wdt:P31  wd:Q5 .
  # Candidates share at least one occupation (P106) with the anchor
  <{iri_str}> wdt:P106 ?occ .
  ?similar wdt:P106 ?occ .
  FILTER(?similar != <{iri_str}>)
  ?similar rdfs:label ?similar_label .
  FILTER(LANG(?similar_label) = "en")
}}
LIMIT {max_k}
"""

    g_uri = _graph_uri("expand_related", [iri_str, text, str(max_k)])
    g = _new_beam_graph(g_uri, text, iteration=0)

    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql},
            headers=_WD_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
    except Exception as exc:
        logger.error("[BEAM_EXPAND_RELATED] SPARQL error: %s", exc)
        return g_uri

    for idx, row in enumerate(bindings, start=1):
        sim_iri = row.get("similar", {}).get("value", "")
        sim_label = row.get("similar_label", {}).get("value", sim_iri)
        # Score: inverse rank (first result = highest score)
        score = 1.0 / float(idx)

        _add_beam_node(
            g,
            mention=sim_label,
            depth=1,
            score=score,
            entity_iri=sim_iri,
            label=sim_label,
            reason="wikidata_sparql_related",
        )

    return g_uri


# ---------------------------------------------------------------------------
# LLM-guided beam search — server-side, single UDF call
# ---------------------------------------------------------------------------


def _expand_entity_wikidata(iri_str: str, limit: int) -> list:
    """Expand a Wikidata entity to similar entities (shared genre + occupation).

    Same SPARQL heuristic as BEAM_EXPAND_RELATED but returns a plain list of
    dicts so it can be called inside the BEAM_LLM_SEARCH loop.
    """
    sparql = (
        "PREFIX wd:   <http://www.wikidata.org/entity/>\n"
        "PREFIX wdt:  <http://www.wikidata.org/prop/direct/>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        f"SELECT DISTINCT ?similar ?similar_label WHERE {{\n"
        f"  <{iri_str}> wdt:P136 ?genre .\n"
        f"  ?similar wdt:P136 ?genre ;\n"
        f"           wdt:P31  wd:Q5 .\n"
        f"  <{iri_str}> wdt:P106 ?occ .\n"
        f"  ?similar wdt:P106 ?occ .\n"
        f"  FILTER(?similar != <{iri_str}>)\n"
        f"  ?similar rdfs:label ?similar_label .\n"
        f"  FILTER(LANG(?similar_label) = \"en\")\n"
        f"}}\n"
        f"LIMIT {limit}\n"
    )
    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql},
            headers=_WD_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        return [
            {
                "entity": row["similar"]["value"],
                "label": row.get("similar_label", {}).get("value", ""),
            }
            for row in bindings
            if "similar" in row
        ]
    except Exception as exc:
        logger.warning("[BEAM_LLM] Wikidata expand failed for %s: %s", iri_str, exc)
        return []


def _expand_entity_neighbors_wikidata(iri_str: str, limit: int) -> list:
    """Strict 1-hop graph expansion over outgoing entity links.

    Returns real graph neighbours linked by direct properties from the anchor.
    This avoids semantic widening based on inferred similarity templates.
    """
    sparql = (
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT DISTINCT ?neighbor ?neighbor_label ?p WHERE {\n"
        f"  <{iri_str}> ?p ?neighbor .\n"
        "  FILTER(isIRI(?neighbor))\n"
        "  FILTER(STRSTARTS(STR(?p), \"http://www.wikidata.org/prop/direct/\"))\n"
        "  OPTIONAL { ?neighbor rdfs:label ?neighbor_label FILTER(LANG(?neighbor_label) = \"en\") }\n"
        "}\n"
        f"LIMIT {limit}\n"
    )
    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql},
            headers=_WD_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        out = []
        for row in bindings:
            if "neighbor" not in row:
                continue
            ent = row["neighbor"].get("value", "")
            lbl = row.get("neighbor_label", {}).get("value", "") or ent.rsplit("/", 1)[-1]
            prop = row.get("p", {}).get("value", "")
            out.append({"entity": ent, "label": lbl, "prop": prop})
        return out
    except Exception as exc:
        logger.warning("[BEAM_LLM] strict expand failed for %s: %s", iri_str, exc)
        return []


def _llm_score_candidates(question: str, candidates: list) -> dict:
    """Ask the configured Groq LLM to score each candidate for relevance.

    Sends a numbered list (label + entity IRI) and expects a JSON object
    mapping entity IRI -> float score [0.0 – 1.0].
    Falls back to {} if the LLM is unavailable or responds unexpectedly.
    """
    import os

    try:
        from groq import Groq
        from SPARQLLM.config import ConfigSingleton
    except ImportError:
        logger.warning("[BEAM_LLM] groq not available — heuristic fallback")
        return {}

    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")

    numbered = "\n".join(
        f'{i}. "{c.get("label", "")}" — {c.get("entity", "")}'
        for i, c in enumerate(candidates, 1)
    )

    prompt = (
        'You are scoring entity candidates for relevance to a question.\n'
        f'Question: "{question}"\n\n'
        f'Candidates:\n{numbered}\n\n'
        'Return a single JSON object mapping each entity IRI to a relevance score '
        'between 0.0 (not relevant) and 1.0 (highly relevant). '
        'Output only the JSON object, no explanation.'
    )

    try:
        groq_client = Groq(api_key=api_key, max_retries=0)
        response = groq_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            parsed = _json.loads(match.group())
            return {str(k): float(v) for k, v in parsed.items()}
    except Exception as exc:
        logger.warning("[BEAM_LLM] LLM scoring failed: %s", exc)

    return {}


def BEAM_LLM_SEARCH(
    question: Any,
    anchor: Any,
    max_steps: Any = 2,
    beam_width: Any = 5,
    expand_k: Any = 12,
    strict_graph: Any = False,
) -> Any:
    """LLM-guided beam search over Wikidata, running entirely server-side.

    At each step the UDF:
      1. Expands every entity in the beam via Wikidata (genre + occupation join)
      2. Deduplicates candidates across all expanded lists
      3. Calls the Groq LLM to score every candidate for relevance to *question*
      4. Keeps only the top *beam_width* by LLM score (heuristic fallback if LLM
         is unavailable)
    The loop repeats *max_steps* times, producing an increasingly refined beam.

    Parameters
    ----------
    question   : natural-language goal / question (string literal)
    anchor     : starting entity — full Wikidata IRI, Q-id string, or a
                 natural-language mention (resolved via WikidataProvider search)
    max_steps  : number of expand→score→prune iterations (default 2)
    beam_width : max candidates to keep after each scoring step (default 5)
    expand_k   : Wikidata neighbours to fetch per beam entity per step (default 12)

    Returns
    -------
    URIRef of a named graph with cand:BeamNode entries ranked by LLM score.
    Each node carries: cand:rank, cand:score, cand:label, cand:entity, cand:reason.
    """
    text = _to_text(question)
    steps = max(1, _to_int(max_steps, 2))
    keep_k = max(1, _to_int(beam_width, 5))
    ex_k = max(1, _to_int(expand_k, 12))
    strict = _to_bool(strict_graph, False)

    # --- Resolve anchor entity ---
    anchor_str = _to_text(anchor)
    if anchor_str.startswith("http://www.wikidata.org/entity/"):
        anchor_iri = anchor_str
        anchor_label = anchor_str.split("/")[-1]
    elif re.match(r"^Q\d+$", anchor_str):
        anchor_iri = f"http://www.wikidata.org/entity/{anchor_str}"
        anchor_label = anchor_str
    else:
        provider = WikidataProvider()
        result = provider.tool_search_entities(search=anchor_str, language="en", limit=1)
        items = result.get("jsonld", {}).get("schema:dataFeedElement", [])
        if items:
            item = items[0].get("schema:item", {})
            anchor_iri = str(item.get("@id", ""))
            lab = item.get("rdfs:label", {})
            anchor_label = (
                lab.get("@value", anchor_str) if isinstance(lab, dict) else anchor_str
            )
        else:
            anchor_iri, anchor_label = "", anchor_str

    # --- Initial beam: only the anchor ---
    beam: list = []
    if anchor_iri:
        beam.append(
            {
                "entity": anchor_iri,
                "label": anchor_label,
                "score": 1.0,
                "depth": 0,
                "reason": "anchor",
            }
        )
    else:
        logger.warning("[BEAM_LLM] Could not resolve anchor '%s'", anchor_str)

    # --- Beam iterations ---
    for step in range(1, steps + 1):
        # Expand — collect distinct neighbours from all current beam entities
        candidates: dict = {}
        for node in beam:
            iri = node.get("entity", "")
            if not iri:
                continue
            expand_fn = _expand_entity_neighbors_wikidata if strict else _expand_entity_wikidata
            for exp in expand_fn(iri, ex_k):
                ent = exp["entity"]
                if ent not in candidates:
                    reason = f"strict_graph_step_{step}" if strict else ""
                    if strict and exp.get("prop"):
                        reason = f"strict_graph_step_{step}:{exp.get('prop')}"
                    candidates[ent] = {
                        "entity": ent,
                        "label": exp["label"],
                        "depth": node["depth"] + 1,
                        "heuristic_rank": len(candidates),
                        "parent_ref": node,
                        "via_property": exp.get("prop") if strict else None,
                        "reason": reason,
                    }

        if not candidates:
            logger.warning("[BEAM_LLM] step %d: no candidates, stopping early", step)
            break

        cand_list = list(candidates.values())

        # LLM scoring
        llm_scores = _llm_score_candidates(text, cand_list)

        for c in cand_list:
            ent = c["entity"]
            llm_s = llm_scores.get(ent, 0.0)
            heur_s = 1.0 / float(c["heuristic_rank"] + 1)
            if llm_s > 0:
                # LLM score dominates; heuristic rank breaks ties
                c["score"] = llm_s * 0.85 + heur_s * 0.15
                if strict:
                    c["reason"] = c.get("reason") or f"llm_strict_step_{step}"
                else:
                    c["reason"] = f"llm_step_{step}"
            else:
                c["score"] = heur_s
                if not c.get("reason"):
                    c["reason"] = f"heuristic_step_{step}"

        cand_list.sort(key=lambda x: x["score"], reverse=True)
        beam = cand_list[:keep_k]

        logger.info(
            "[BEAM_LLM] step %d/%d: %d candidates -> kept %d (top: %s %.3f, %s)",
            step, steps, len(cand_list), len(beam),
            beam[0]["label"] if beam else "-",
            beam[0]["score"] if beam else 0.0,
            beam[0].get("reason", "?") if beam else "-",
        )

    # --- Materialise results into a named graph ---
    g_uri = _graph_uri(
        "llm_beam",
        [text, anchor_str, str(steps), str(keep_k), str(ex_k), str(int(strict))],
    )
    g = _new_beam_graph(g_uri, text, iteration=steps)

    emitted: dict[int, BNode] = {}

    def _emit_path_node(node_dict: dict[str, Any]) -> BNode:
        key = id(node_dict)
        if key in emitted:
            return emitted[key]

        parent_bn = None
        parent_ref = node_dict.get("parent_ref")
        if isinstance(parent_ref, dict):
            parent_bn = _emit_path_node(parent_ref)

        bn = _add_beam_node(
            g,
            mention=node_dict.get("label") or "",
            depth=int(node_dict.get("depth", steps)),
            score=float(node_dict.get("score", 0.0)),
            parent=parent_bn,
            entity_iri=node_dict.get("entity"),
            label=node_dict.get("label"),
            reason=node_dict.get("reason"),
        )
        via_prop = node_dict.get("via_property")
        if via_prop:
            g.add((bn, CAND.viaProperty, URIRef(str(via_prop))))

        emitted[key] = bn
        return bn

    for rank, node in enumerate(beam, start=1):
        bn = _emit_path_node(node)
        g.add((bn, CAND.rank, Literal(rank, datatype=XSD.integer)))
        g.add((bn, CAND.isLeaf, Literal(True, datatype=XSD.boolean)))
        if rank == 1:
            g.add((bn, CAND.isBest, Literal(True, datatype=XSD.boolean)))

    logger.info("[BEAM_LLM] done — graph %s with %d nodes", g_uri, len(beam))
    return g_uri


def _extract_anchor_bracket(question: str) -> str | None:
    m = re.search(r"\[([^\]]+)\]", question)
    if not m:
        return None
    return m.group(1).strip()


def _metaqa_label_predicate() -> URIRef:
    return URIRef("http://metaqa.org/schema/label")


def _label_in_graph(src: Graph, entity: URIRef) -> str:
    lp = _metaqa_label_predicate()
    for _, _, o in src.triples((entity, lp, None)):
        return str(o)
    s = str(entity)
    return s.rsplit("/", 1)[-1]


def _find_metaqa_anchor(src: Graph, anchor_label: str) -> tuple[str | None, str]:
    lp = _metaqa_label_predicate()
    target = anchor_label.strip().lower()
    for s, _, o in src.triples((None, lp, None)):
        if str(o).strip().lower() == target:
            return str(s), str(o)
    return None, anchor_label


def _predicate_slug(p: URIRef) -> str:
    return str(p).rsplit("/", 1)[-1].lower()


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


def _expand_local_metaqa(src: Graph, entity_iri: str, limit: int) -> list[dict[str, str]]:
    e = URIRef(entity_iri)
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    # outgoing 1-hop
    for _, p, o in src.triples((e, None, None)):
        if not isinstance(o, URIRef):
            continue
        item = (str(o), str(p), "out")
        if item in seen:
            continue
        seen.add(item)
        candidates.append(
            {
                "entity": str(o),
                "label": _label_in_graph(src, o),
                "prop": str(p),
                "direction": "out",
            }
        )
        if len(candidates) >= limit:
            return candidates

    # incoming 1-hop
    for s, p, _ in src.triples((None, None, e)):
        if not isinstance(s, URIRef):
            continue
        item = (str(s), str(p), "in")
        if item in seen:
            continue
        seen.add(item)
        candidates.append(
            {
                "entity": str(s),
                "label": _label_in_graph(src, s),
                "prop": str(p),
                "direction": "in",
            }
        )
        if len(candidates) >= limit:
            break

    return candidates


def BEAM_METAQA_SEARCH(
    question: Any,
    g_source: Any,
    max_steps: Any = 2,
    beam_width: Any = 20,
    expand_k: Any = 50,
) -> Any:
    """Beam-search-like local exploration for MetaQA questions.

    This variant does not call Wikidata and only expands on a local graph
    (e.g. a MetaQA TTL loaded with ggf:LOAD).
    """
    text = _to_text(question)
    src = store.get_context(g_source)
    steps = max(1, _to_int(max_steps, 2))
    keep_k = max(1, _to_int(beam_width, 20))
    ex_k = max(1, _to_int(expand_k, 50))

    anchor_name = _extract_anchor_bracket(text)
    if not anchor_name:
        mentions = _extract_mentions(text, max_mentions=1)
        anchor_name = mentions[0] if mentions else ""

    anchor_iri, anchor_label = _find_metaqa_anchor(src, anchor_name)

    beam: list[dict[str, Any]] = []
    if anchor_iri:
        beam.append(
            {
                "entity": anchor_iri,
                "label": anchor_label,
                "score": 1.0,
                "depth": 0,
                "reason": "metaqa_anchor",
                "parent_ref": None,
                "via_property": None,
                "via_direction": None,
            }
        )

    rel_hints = _question_relation_hints(text)

    for step in range(1, steps + 1):
        candidates: dict[str, dict[str, Any]] = {}

        for parent in beam:
            parent_iri = parent.get("entity", "")
            if not parent_iri:
                continue
            for idx, exp in enumerate(_expand_local_metaqa(src, parent_iri, ex_k), start=1):
                ent = exp["entity"]
                if ent == anchor_iri:
                    continue
                if ent in candidates:
                    continue

                slug = _predicate_slug(URIRef(exp["prop"]))
                hint_bonus = 0.5 if slug in rel_hints else 0.0
                dir_bonus = 0.1 if exp.get("direction") == "in" else 0.0
                base = 1.0 / float(idx + 1)
                score = float(parent.get("score", 0.0)) * 0.5 + base * 0.3 + hint_bonus + dir_bonus

                candidates[ent] = {
                    "entity": ent,
                    "label": exp["label"],
                    "depth": int(parent.get("depth", 0)) + 1,
                    "score": score,
                    "reason": f"metaqa_step_{step}:{exp['prop']}",
                    "parent_ref": parent,
                    "via_property": exp["prop"],
                    "via_direction": exp.get("direction"),
                }

        if not candidates:
            break

        beam = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:keep_k]

    g_uri = _graph_uri(
        "metaqa_beam",
        [text, str(g_source), anchor_name or "", str(steps), str(keep_k), str(ex_k)],
    )
    g = _new_beam_graph(g_uri, text, iteration=steps)

    emitted: dict[int, BNode] = {}

    def _emit(node_dict: dict[str, Any]) -> BNode:
        key = id(node_dict)
        if key in emitted:
            return emitted[key]

        parent_bn = None
        if isinstance(node_dict.get("parent_ref"), dict):
            parent_bn = _emit(node_dict["parent_ref"])

        bn = _add_beam_node(
            g,
            mention=node_dict.get("label") or "",
            depth=int(node_dict.get("depth", 0)),
            score=float(node_dict.get("score", 0.0)),
            parent=parent_bn,
            entity_iri=node_dict.get("entity"),
            label=node_dict.get("label"),
            reason=node_dict.get("reason"),
        )
        if node_dict.get("via_property"):
            g.add((bn, CAND.viaProperty, URIRef(str(node_dict["via_property"]))))
        if node_dict.get("via_direction"):
            g.add((bn, CAND.viaDirection, Literal(str(node_dict["via_direction"]))))

        emitted[key] = bn
        return bn

    for rank, node in enumerate(beam, start=1):
        bn = _emit(node)
        g.add((bn, CAND.rank, Literal(rank, datatype=XSD.integer)))
        g.add((bn, CAND.isLeaf, Literal(True, datatype=XSD.boolean)))
        if rank == 1:
            g.add((bn, CAND.isBest, Literal(True, datatype=XSD.boolean)))

    return g_uri
