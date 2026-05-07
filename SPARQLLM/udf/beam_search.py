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


def _beam_leaf_candidates_for_answer(g_in: Graph, top_k: int) -> list[dict[str, Any]]:
    """Return top-k leaf candidates with rank/score and relevant facts."""
    nodes = _beam_nodes(g_in)
    node_by_subject = {n.get("node"): n for n in nodes}

    leaf_subjects = {
        s for s, _, o in g_in.triples((None, CAND.isLeaf, None)) if str(o).strip().lower() == "true"
    }
    subjects = list(leaf_subjects) if leaf_subjects else list(node_by_subject.keys())

    out: list[dict[str, Any]] = []
    for s in subjects:
        node = node_by_subject.get(s)
        if not node:
            continue

        rank_val = None
        for _, _, r in g_in.triples((s, CAND.rank, None)):
            try:
                rank_val = int(str(r))
            except Exception:
                rank_val = None
            break

        facts = [str(f) for _, _, f in g_in.triples((s, CAND.relevantFact, None))]
        out.append(
            {
                "node": s,
                "entity": str(node.get("entity")) if node.get("entity") else "",
                "label": str(node.get("label") or node.get("mention") or ""),
                "score": float(node.get("score") or 0.0),
                "rank": rank_val,
                "facts": facts,
            }
        )

    # Prefer explicit rank when available, fallback to score-desc.
    def _sort_key(x: dict[str, Any]) -> tuple[float, float]:
        r = float(x["rank"]) if x.get("rank") is not None else 1e9
        s = -float(x.get("score", 0.0))
        return (r, s)

    out.sort(key=_sort_key)
    return out[:top_k]


def _llm_pick_from_beam(question: str, candidates: list[dict[str, Any]]) -> tuple[str, str]:
    """Ask LLM to pick the best candidate label from beam candidates.

    Returns (selected_name, answer_text). selected_name can be "NONE".
    """
    import os

    if not candidates:
        return "NONE", "NONE"

    try:
        from groq import Groq
        from SPARQLLM.config import ConfigSingleton
    except ImportError:
        logger.warning("[BEAM_FINAL_ANSWER] groq not available")
        return "NONE", "NONE"

    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")

    allowed = [c.get("label", "") for c in candidates if c.get("label")]
    allowed_str = " | ".join(allowed)
    evidence_lines = []
    for c in candidates:
        label = c.get("label", "")
        entity = c.get("entity", "")
        score = float(c.get("score", 0.0))
        facts = c.get("facts", [])[:8]
        facts_txt = "; ".join(facts) if facts else "(no facts)"
        evidence_lines.append(f"- {label} ({entity}) score={score:.3f} :: {facts_txt}")

    prompt = (
        "Answer the question using ONLY the candidate list and evidence below.\n"
        "Do NOT invent entities. If none applies, choose NONE.\n\n"
        f'Question: "{question}"\n'
        f"Candidates: {allowed_str}\n\n"
        "Candidate evidence:\n"
        f"{"\n".join(evidence_lines)}\n\n"
        "Return ONLY this JSON-LD object (no extra text):\n"
        "{\n"
        "  \"@context\": \"https://schema.org/\",\n"
        "  \"@type\": \"Answer\",\n"
        "  \"text\": \"one concise sentence\",\n"
        "  \"name\": \"one candidate from the list, or NONE\"\n"
        "}\n"
    )

    try:
        client = Groq(api_key=api_key, max_retries=0)
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            parsed = _json.loads(m.group())
            name = str(parsed.get("name", "NONE") or "NONE")
            text_out = str(parsed.get("text", "NONE") or "NONE")
            # Guardrail: force selection to allowed candidates or NONE
            allowed_l = {x.lower(): x for x in allowed}
            if name.lower() in allowed_l:
                name = allowed_l[name.lower()]
            elif name.strip().upper() == "NONE":
                name = "NONE"
            else:
                name = "NONE"
            return name, text_out
    except Exception as exc:
        logger.warning("[BEAM_FINAL_ANSWER] LLM answer failed: %s", exc)

    return "NONE", "NONE"


def BEAM_FINAL_ANSWER(question: Any, g_beam: Any, top_k: Any = 20) -> Any:
    """Generate a final schema:Answer graph directly from a beam graph.

    Parameters
    ----------
    question: natural-language question
    g_beam:   beam graph URI (e.g., output of TOG-LOCAL or BEAM-BEST)
    top_k:    max candidate leaves used for final answer generation
    """
    text = _to_text(question)
    keep_k = max(1, _to_int(top_k, 20))
    g_in = store.get_context(g_beam)
    cands = _beam_leaf_candidates_for_answer(g_in, keep_k)
    selected_name, answer_text = _llm_pick_from_beam(text, cands)

    g_uri = _graph_uri("beam_final_answer", [text, str(g_beam), str(keep_k)])
    g = store.get_context(g_uri)
    g.bind("schema", SCHEMA)
    g.bind("cand", CAND)

    ans = URIRef(str(g_uri) + "#answer")
    g.add((ans, RDF.type, SCHEMA.Answer))
    g.add((ans, SCHEMA.text, Literal(answer_text)))
    g.add((ans, SCHEMA.name, Literal(selected_name)))
    g.add((ans, CAND.question, Literal(text)))
    g.add((ans, CAND.sourceBeam, URIRef(str(g_beam))))

    for rank, c in enumerate(cands, start=1):
        n = BNode()
        g.add((n, RDF.type, CAND.BeamNode))
        if c.get("entity"):
            g.add((n, CAND.entity, URIRef(c["entity"])))
        if c.get("label"):
            g.add((n, CAND.label, Literal(c["label"])))
        g.add((n, CAND.score, Literal(round(float(c.get("score", 0.0)), 6), datatype=XSD.decimal)))
        g.add((n, CAND.rank, Literal(rank, datatype=XSD.integer)))
        for f in c.get("facts", [])[:8]:
            g.add((n, CAND.relevantFact, Literal(str(f))))
        g.add((ans, CAND.candidate, n))

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
    4. Keeps only the top *beam_width* by LLM score.
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

        scored: list[dict[str, Any]] = []
        for c in cand_list:
            ent = c["entity"]
            llm_s = float(llm_scores.get(ent, 0.0))
            if llm_s <= 0.0:
                continue
            c["score"] = llm_s
            if strict:
                c["reason"] = c.get("reason") or f"llm_strict_step_{step}"
            else:
                c["reason"] = f"llm_step_{step}"
            scored.append(c)

        if not scored:
            logger.warning("[BEAM_LLM] step %d: no LLM-scored candidates, stopping early", step)
            break

        scored.sort(key=lambda x: x["score"], reverse=True)
        beam = scored[:keep_k]

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


def _resolve_local_metaqa_anchor(src: Graph, anchor: Any, question_text: str) -> tuple[str | None, str, str]:
    anchor_str = _to_text(anchor)
    if anchor_str.startswith("http://") or anchor_str.startswith("https://"):
        label = _label_in_graph(src, URIRef(anchor_str))
        return anchor_str, label, label

    if anchor_str:
        anchor_iri, anchor_label = _find_metaqa_anchor(src, anchor_str)
        return anchor_iri, anchor_label, anchor_str

    anchor_name = _extract_anchor_bracket(question_text)
    if not anchor_name:
        mentions = _extract_mentions(question_text, max_mentions=1)
        anchor_name = mentions[0] if mentions else ""

    anchor_iri, anchor_label = _find_metaqa_anchor(src, anchor_name)
    return anchor_iri, anchor_label, anchor_name


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


def _collect_relevant_entity_facts(
    src: Graph,
    entity_iri: str,
    question: str,
    max_per_relation: int = 3,
    max_total: int = 12,
) -> list[str]:
    """Collect question-relevant 1-hop facts for an entity.

    Facts are formatted as compact strings and used both for ToG prompts and
    for materialization in the beam graph for debugging/inspection.
    """
    e = URIRef(entity_iri)
    hints = _question_relation_hints(question)

    # Keep always-useful answer-bearing relations for MetaQA even if hints miss.
    target_relations = set(hints) | {
        "in_language",
        "has_genre",
        "release_year",
        "starred_actors",
        "directed_by",
        "written_by",
    }

    facts: list[str] = []
    per_rel_count: dict[tuple[str, str], int] = {}

    # Outgoing facts: entity --p--> value
    for _, p, o in src.triples((e, None, None)):
        slug = _predicate_slug(URIRef(str(p)))
        if slug not in target_relations:
            continue
        key = ("out", slug)
        if per_rel_count.get(key, 0) >= max_per_relation:
            continue

        if isinstance(o, URIRef):
            val = _label_in_graph(src, o)
        else:
            val = str(o)

        facts.append(f"out:{slug}={val}")
        per_rel_count[key] = per_rel_count.get(key, 0) + 1
        if len(facts) >= max_total:
            return facts

    # Incoming facts: source --p--> entity
    for s, p, _ in src.triples((None, None, e)):
        if not isinstance(s, URIRef):
            continue
        slug = _predicate_slug(URIRef(str(p)))
        if slug not in target_relations:
            continue
        key = ("in", slug)
        if per_rel_count.get(key, 0) >= max_per_relation:
            continue

        val = _label_in_graph(src, s)
        facts.append(f"in:{slug}={val}")
        per_rel_count[key] = per_rel_count.get(key, 0) + 1
        if len(facts) >= max_total:
            return facts

    return facts


def _expand_local_metaqa(
    src: Graph,
    entity_iri: str,
    limit: int,
    include_literal_terminals: bool = False,
) -> list[dict[str, str]]:
    e = URIRef(entity_iri)
    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    # outgoing 1-hop
    for _, p, o in src.triples((e, None, None)):
        if isinstance(o, URIRef):
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
                    "is_literal": False,
                }
            )
        elif include_literal_terminals:
            literal_key = f"literal:{str(p)}:{str(o)}"
            item = (literal_key, str(p), "out")
            if item in seen:
                continue
            seen.add(item)
            candidates.append(
                {
                    "entity": literal_key,
                    "label": str(o),
                    "prop": str(p),
                    "direction": "out",
                    "is_literal": True,
                }
            )
        else:
            continue

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
                "is_literal": False,
            }
        )
        if len(candidates) >= limit:
            break

    return candidates


def BEAM_LLM_SEARCH_LOCAL(
    question: Any,
    anchor: Any,
    g_source: Any,
    max_steps: Any = 2,
    beam_width: Any = 20,
    expand_k: Any = 50,
) -> Any:
    """LLM-guided beam search over a local MetaQA-style graph.

    This variant keeps the local graph expansion used by BEAM_METAQA_SEARCH,
    but takes an explicit anchor and scores each frontier against the question
    with the same LLM scorer used by BEAM_LLM_SEARCH.
    Candidates are kept only when they receive a positive LLM score.
    """
    text = _to_text(question)
    src = store.get_context(g_source)
    steps = max(1, _to_int(max_steps, 2))
    keep_k = max(1, _to_int(beam_width, 20))
    ex_k = max(1, _to_int(expand_k, 50))

    anchor_iri, anchor_label, anchor_name = _resolve_local_metaqa_anchor(src, anchor, text)

    beam: list[dict[str, Any]] = []
    if anchor_iri:
        beam.append(
            {
                "entity": anchor_iri,
                "label": anchor_label,
                "score": 1.0,
                "depth": 0,
                "reason": "local_anchor",
                "parent_ref": None,
                "via_property": None,
                "via_direction": None,
            }
        )
    else:
        logger.warning("[BEAM_LLM_LOCAL] Could not resolve anchor '%s'", anchor_name)

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

                slug = _predicate_slug(URIRef(exp["prop"]))
                hint_bonus = 0.5 if slug in rel_hints else 0.0
                dir_bonus = 0.1 if exp.get("direction") == "in" else 0.0
                base = 1.0 / float(idx + 1)
                heur_s = (
                    float(parent.get("score", 0.0)) * 0.5 + base * 0.3 + hint_bonus + dir_bonus
                )

                existing = candidates.get(ent)
                if existing and heur_s <= float(existing.get("heuristic_score", 0.0)):
                    continue

                candidates[ent] = {
                    "entity": ent,
                    "label": exp["label"],
                    "depth": int(parent.get("depth", 0)) + 1,
                    "heuristic_score": heur_s,
                    "heuristic_rank": idx,
                    "parent_ref": parent,
                    "via_property": exp["prop"],
                    "via_direction": exp.get("direction"),
                    "reason": f"local_heuristic_step_{step}:{exp['prop']}",
                }

        if not candidates:
            logger.warning("[BEAM_LLM_LOCAL] step %d: no candidates, stopping early", step)
            break

        cand_list = list(candidates.values())
        llm_scores = _llm_score_candidates(text, cand_list)

        scored: list[dict[str, Any]] = []
        for c in cand_list:
            ent = c["entity"]
            llm_s = float(llm_scores.get(ent, 0.0))
            if llm_s <= 0.0:
                continue
            c["score"] = llm_s
            c["reason"] = f"llm_local_step_{step}:{c['via_property']}"
            scored.append(c)

        if not scored:
            logger.warning(
                "[BEAM_LLM_LOCAL] step %d: no LLM-scored candidates, stopping early",
                step,
            )
            break

        scored.sort(key=lambda x: x["score"], reverse=True)
        beam = scored[:keep_k]

        logger.info(
            "[BEAM_LLM_LOCAL] step %d/%d: %d candidates -> kept %d (top: %s %.3f, %s)",
            step,
            steps,
            len(cand_list),
            len(beam),
            beam[0]["label"] if beam else "-",
            beam[0]["score"] if beam else 0.0,
            beam[0].get("reason", "?") if beam else "-",
        )

    g_uri = _graph_uri(
        "llm_local_beam",
        [text, str(anchor), str(g_source), anchor_name or "", str(steps), str(keep_k), str(ex_k)],
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

    logger.info("[BEAM_LLM_LOCAL] done — graph %s with %d nodes", g_uri, len(beam))
    return g_uri




def BEAM_METAQA_SEARCH(
    question: Any,
    g_source: Any,
    max_steps: Any = 2,
    beam_width: Any = 20,
    expand_k: Any = 50,
) -> Any:
    """Run a local beam search over a MetaQA-style knowledge graph.

    Abstract algorithm:
      1. Identify an anchor entity from the question.
      2. Resolve that anchor in the local RDF graph.
      3. Initialize the beam with the resolved anchor node.
      4. For each search step:
         - expand each beam node to its local one-hop neighbours,
         - score each candidate using simple path heuristics,
         - deduplicate candidates by entity,
         - keep only the top candidates up to the beam width.
      5. Materialize the final beam as an RDF graph containing ranked leaf
         nodes together with their parent links, traversed properties, and
         traversal directions.

    This variant performs only local graph expansion and does not query
    Wikidata.
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


# ---------------------------------------------------------------------------
# CBD-based LLM scoring (NEW VARIANT)
# ---------------------------------------------------------------------------


def _build_cbd(src: Graph, entity_iri: str, depth: int = 1) -> dict[str, Any]:
    """Build a Concise Bounded Description of an entity.

    Returns a dict with:
      - entity: the target entity IRI
      - label: entity label
      - outgoing: list of {property, target_label} for outgoing URIRef links
      - incoming: list of {property, source_label} for incoming URIRef links
    """
    e = URIRef(entity_iri)
    label = _label_in_graph(src, e)

    outgoing = []
    seen_out = set()
    for _, p, o in src.triples((e, None, None)):
        if not isinstance(o, URIRef):
            continue
        key = (str(p), str(o))
        if key in seen_out:
            continue
        seen_out.add(key)
        prop_name = str(p).rsplit("/", 1)[-1]
        target_label = _label_in_graph(src, o)
        outgoing.append({
            "property": prop_name,
            "target": target_label,
        })

    incoming = []
    seen_in = set()
    for s, p, _ in src.triples((None, None, e)):
        if not isinstance(s, URIRef):
            continue
        key = (str(p), str(s))
        if key in seen_in:
            continue
        seen_in.add(key)
        prop_name = str(p).rsplit("/", 1)[-1]
        source_label = _label_in_graph(src, s)
        incoming.append({
            "property": prop_name,
            "source": source_label,
        })

    return {
        "entity": entity_iri,
        "label": label,
        "outgoing": outgoing,
        "incoming": incoming,
    }


def _summarize_cbd_to_text(cbd: dict[str, Any]) -> str:
    """Convert CBD dict to a concise text summary for LLM context.

    Format: "Entity: outgoing links | incoming links"
    Example: "Alien: genre=[SciFi], language=[English] | appears_in=[Blade Runner]"
    """
    label = cbd.get("label", "?")
    parts = [label]

    out = cbd.get("outgoing", [])
    if out:
        out_strs = [f"{item['property']}=[{item['target']}]" for item in out[:5]]
        parts.append("out:" + ",".join(out_strs))

    inc = cbd.get("incoming", [])
    if inc:
        inc_strs = [f"{item['property']}=[{item['source']}]" for item in inc[:5]]
        parts.append("in:" + ",".join(inc_strs))

    return " | ".join(parts)


def _llm_score_candidates_with_cbd(question: str, candidates_with_cbd: list) -> dict:
    """Ask LLM to score candidates as progress toward answering a question.

    Each candidate dict should have:
      - entity: IRI
      - label: entity label
      - cbd_summary: text summary of local RDF context
      - from_label: parent node label (optional but recommended)
      - via_property: traversed edge/property from parent (optional)
      - via_direction: edge direction, "out" or "in" (optional)
    """
    import os

    try:
        from groq import Groq
        from SPARQLLM.config import ConfigSingleton
    except ImportError:
        logger.warning("[BEAM_LLM_CBD] groq not available")
        return {}

    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")

    numbered = "\n".join(
        f'{i}. Candidate: {c.get("label", "")} - {c.get("entity", "")}\n'
        f'   Step from: {c.get("from_label", "?")} --{c.get("via_property", "?")} ({c.get("via_direction", "?")})--> {c.get("label", "?")}\n'
        f'   Local context: {c.get("cbd_summary", "")}'
        for i, c in enumerate(candidates_with_cbd, 1)
    )

    prompt = (
        "You are scoring beam-search candidates by PROGRESS toward answering a question.\n"
        "The candidate does not need to be the final answer itself.\n"
        "Score whether moving from the parent node to this candidate is a useful intermediate step.\n"
        "Each candidate includes traversal edge and local RDF context.\n"
        f'Question: "{question}"\n\n'
        f"Candidates:\n{numbered}\n\n"
        "Scoring rubric:\n"
        "- 1.0: strong progress (clearly moves toward answer type/constraints)\n"
        "- 0.7: moderate progress (plausibly useful intermediate node)\n"
        "- 0.3: weak progress (loosely related, unlikely to help)\n"
        "- 0.0: no progress or distractor\n\n"
        "Important: prefer candidates whose relation/direction and context align with the question intent "
        "(e.g., release year, genre, language, actor, director).\n"
        "Return a single JSON object mapping each entity IRI to a score in [0.0, 1.0]. "
        "Output only the JSON object, no explanation."
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
        logger.warning("[BEAM_LLM_CBD] LLM scoring failed: %s", exc)

    return {}


def BEAM_LLM_SEARCH_LOCAL_WITH_CBD(
    question: Any,
    anchor: Any,
    g_source: Any,
    max_steps: Any = 2,
    beam_width: Any = 20,
    expand_k: Any = 50,
) -> Any:
    """LLM-guided beam search with Concise Bounded Description context.

    This variant combines local graph expansion with CBD-based LLM scoring.
    At each step:
      1. Expand each beam node to 1-hop neighbours (URIRef only)
      2. Build CBD (Concise Bounded Description) for each candidate
      3. Summarize CBD to text for LLM context
      4. Score each candidate with LLM (given question + CBD summary)
      5. Keep only top-k by LLM score (>0.0)

    Parameters
    ----------
    question   : natural-language goal / question
    anchor     : starting entity (resolved in the local graph)
    g_source   : reference to local RDF graph
    max_steps  : number of expand→score→prune iterations (default 2)
    beam_width : max candidates after each scoring step (default 20)
    expand_k   : local neighbours to fetch per beam entity (default 50)

    Returns
    -------
    URIRef of a named graph with cand:BeamNode entries ranked by LLM score.
    """
    text = _to_text(question)
    src = store.get_context(g_source)
    steps = max(1, _to_int(max_steps, 2))
    keep_k = max(1, _to_int(beam_width, 20))
    ex_k = max(1, _to_int(expand_k, 50))

    anchor_iri, anchor_label, anchor_name = _resolve_local_metaqa_anchor(src, anchor, text)

    beam: list[dict[str, Any]] = []
    if anchor_iri:
        beam.append(
            {
                "entity": anchor_iri,
                "label": anchor_label,
                "score": 1.0,
                "depth": 0,
                "reason": "local_anchor_cbd",
                "parent_ref": None,
                "via_property": None,
                "via_direction": None,
            }
        )
    else:
        logger.warning("[BEAM_LLM_CBD] Could not resolve anchor '%s'", anchor_name)

    for step in range(1, steps + 1):
        candidates: dict[str, dict[str, Any]] = {}

        for parent in beam:
            parent_iri = parent.get("entity", "")
            if not parent_iri:
                continue

            for exp in _expand_local_metaqa(src, parent_iri, ex_k):
                ent = exp["entity"]
                if ent == anchor_iri or ent in candidates:
                    continue

                candidates[ent] = {
                    "entity": ent,
                    "label": exp["label"],
                    "depth": int(parent.get("depth", 0)) + 1,
                    "parent_ref": parent,
                    "from_label": parent.get("label", ""),
                    "via_property": exp["prop"],
                    "via_direction": exp.get("direction"),
                    "reason": f"cbd_step_{step}:{exp['prop']}",
                }

        if not candidates:
            logger.warning("[BEAM_LLM_CBD] step %d: no candidates, stopping early", step)
            break

        cand_list = list(candidates.values())

        # Build CBD + summarize for each candidate
        for c in cand_list:
            cbd = _build_cbd(src, c["entity"], depth=1)
            c["cbd_summary"] = _summarize_cbd_to_text(cbd)

        # LLM scoring with CBD context
        llm_scores = _llm_score_candidates_with_cbd(text, cand_list)

        scored: list[dict[str, Any]] = []
        for c in cand_list:
            ent = c["entity"]
            llm_s = float(llm_scores.get(ent, 0.0))
            if llm_s <= 0.0:
                continue
            c["score"] = llm_s
            scored.append(c)

        if not scored:
            logger.warning("[BEAM_LLM_CBD] step %d: no LLM-scored candidates, stopping early", step)
            break

        scored.sort(key=lambda x: x["score"], reverse=True)
        beam = scored[:keep_k]

        logger.info(
            "[BEAM_LLM_CBD] step %d/%d: %d candidates -> kept %d (top: %s %.3f)",
            step,
            steps,
            len(cand_list),
            len(beam),
            beam[0]["label"] if beam else "-",
            beam[0]["score"] if beam else 0.0,
        )

    # Materialize results
    g_uri = _graph_uri(
        "llm_cbd_beam",
        [text, str(anchor), str(g_source), anchor_name or "", str(steps), str(keep_k), str(ex_k)],
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

    logger.info("[BEAM_LLM_CBD] done — graph %s with %d nodes", g_uri, len(beam))
    return g_uri


def _relation_signature(direction: str, prop_iri: str) -> tuple[str, str]:
    return (direction, _predicate_slug(URIRef(prop_iri)))


def _format_schema_path(path_sig: tuple[tuple[str, str], ...]) -> str:
    if not path_sig:
        return "(empty)"
    return " -> ".join(f"{d}:{r}" for d, r in path_sig)


def _sample_schema_paths_local(
    src: Graph,
    anchor_iri: str,
    max_depth: int,
    expand_k: int,
    max_paths: int,
) -> list[tuple[tuple[str, str], ...]]:
    """Sample relation-path signatures (schema-level) from local DFS walks."""
    root = URIRef(anchor_iri)
    stack: list[tuple[URIRef, list[tuple[str, str]], set[str]]] = [(root, [], {anchor_iri})]
    path_counts: dict[tuple[tuple[str, str], ...], int] = {}

    while stack and len(path_counts) < max_paths:
        node, rel_path, visited = stack.pop()
        if len(rel_path) >= max_depth:
            continue

        expansions = _expand_local_metaqa(src, str(node), expand_k, include_literal_terminals=True)
        for exp in expansions:
            ent = exp.get("entity", "")
            if not ent or ent in visited:
                continue

            sig = _relation_signature(exp.get("direction", "out"), exp.get("prop", ""))
            new_path = tuple(rel_path + [sig])
            path_counts[new_path] = path_counts.get(new_path, 0) + 1

            if len(new_path) < max_depth and not bool(exp.get("is_literal", False)):
                stack.append((URIRef(ent), list(new_path), visited | {ent}))

            if len(path_counts) >= max_paths:
                break

    return sorted(path_counts.keys(), key=lambda p: (len(p), -path_counts.get(p, 0)))


def _score_schema_path(question: str, path_sig: tuple[tuple[str, str], ...]) -> float:
    """Heuristic score of a schema path against question intent."""
    q = question.lower()
    rel_hints = _question_relation_hints(question)
    rels = [slug for _, slug in path_sig]

    score = 0.1
    if any(r in rel_hints for r in rels):
        score += 0.6

    # reward if final edge resembles expected answer relation
    if rels:
        last = rels[-1]
        if "year" in q and "year" in last:
            score += 0.4
        if "who" in q and last in {"starred_actors", "directed_by", "written_by"}:
            score += 0.4
        if "language" in q and "language" in last:
            score += 0.4
        if ("genre" in q or "type" in q) and "genre" in last:
            score += 0.4

    # slight preference for 2-hop on MetaQA-2hop tasks
    if len(path_sig) == 2:
        score += 0.2
    elif len(path_sig) == 3:
        score += 0.1

    return min(1.0, max(0.0, score))


def _follow_schema_path_local(
    src: Graph,
    anchor_node: dict[str, Any],
    path_sig: tuple[tuple[str, str], ...],
    per_step_expand_k: int,
) -> list[dict[str, Any]]:
    """Traverse local graph constrained by a relation signature path."""
    frontier: list[dict[str, Any]] = [anchor_node]

    for step_idx, (wanted_dir, wanted_slug) in enumerate(path_sig, start=1):
        nxt: list[dict[str, Any]] = []
        seen_step: set[str] = set()

        for parent in frontier:
            parent_iri = parent.get("entity", "")
            if not parent_iri:
                continue

            for exp in _expand_local_metaqa(src, parent_iri, per_step_expand_k):
                ent = exp.get("entity", "")
                if not ent or ent in seen_step:
                    continue

                exp_dir = exp.get("direction", "out")
                exp_slug = _predicate_slug(URIRef(exp.get("prop", "")))
                if exp_dir != wanted_dir or exp_slug != wanted_slug:
                    continue

                seen_step.add(ent)
                nxt.append(
                    {
                        "entity": ent,
                        "label": exp.get("label", ""),
                        "depth": int(parent.get("depth", 0)) + 1,
                        "parent_ref": parent,
                        "from_label": parent.get("label", ""),
                        "via_property": exp.get("prop"),
                        "via_direction": exp_dir,
                        "reason": f"dfs_schema_step_{step_idx}:{exp.get('prop', '')}",
                    }
                )

        frontier = nxt
        if not frontier:
            break

    return frontier


def BEAM_DFS_SCHEMA_LOCAL(
    question: Any,
    anchor: Any,
    g_source: Any,
    max_depth: Any = 3,
    beam_width: Any = 20,
    expand_k: Any = 50,
) -> Any:
    """Materialize 0-hop..N-hop schema paths for a local MetaQA graph.

    This UDF now focuses on schema construction only:
      1. Resolve anchor in local graph
      2. Sample relation-path signatures with DFS up to max_depth
      3. Materialize unique 0-hop, 1-hop, ... N-hop schema paths into a graph

    Any reranking or path selection is expected to happen in downstream UDFs
    such as METAQA_SCHEMA_TO_SPARQL.
    """
    text = _to_text(question)
    src = store.get_context(g_source)
    depth = max(1, _to_int(max_depth, 3))
    keep_k = max(1, _to_int(beam_width, 20))
    ex_k = max(1, _to_int(expand_k, 50))

    anchor_iri, anchor_label, anchor_name = _resolve_local_metaqa_anchor(src, anchor, text)
    root_node: dict[str, Any] = {
        "entity": anchor_iri,
        "label": anchor_label,
        "score": 1.0,
        "depth": 0,
        "reason": "dfs_schema_anchor",
        "parent_ref": None,
        "via_property": None,
        "via_direction": None,
        "from_label": "",
    }

    if not anchor_iri:
        logger.warning("[BEAM_DFS_SCHEMA_LOCAL] Could not resolve anchor '%s'", anchor_name)
        g_uri = _graph_uri("dfs_schema_local", [text, str(anchor), str(g_source), "empty"])
        _new_beam_graph(g_uri, text, iteration=0)
        return g_uri

    sampled = _sample_schema_paths_local(
        src=src,
        anchor_iri=anchor_iri,
        max_depth=depth,
        expand_k=min(ex_k, 80),
        max_paths=max(80, keep_k * 8),
    )
    logger.info(
        "[BEAM_DFS_SCHEMA_LOCAL] sampled %d schema paths (anchor=%s, max_depth=%d)",
        len(sampled),
        anchor_label,
        depth,
    )
    for i, p in enumerate(sampled[:20], start=1):
        logger.debug(
            "[BEAM_DFS_SCHEMA_LOCAL] sampled[%d]: %s",
            i,
            _format_schema_path(p),
        )

    g_uri = _graph_uri(
        "dfs_schema_local",
        [text, str(anchor), str(g_source), anchor_name or "", str(depth), str(keep_k), str(ex_k)],
    )
    g = _new_beam_graph(g_uri, text, iteration=depth)

    meta = URIRef(str(g_uri) + "#schema-root")
    g.add((meta, RDF.type, CAND.SchemaSearch))
    g.add((meta, CAND.anchor, Literal(anchor_name or anchor_label)))
    if anchor_iri:
        g.add((meta, CAND.entity, URIRef(anchor_iri)))

    anchor_bn = _add_beam_node(
        g,
        mention=anchor_label,
        depth=0,
        score=1.0,
        parent=None,
        entity_iri=anchor_iri,
        label=anchor_label,
        reason="dfs_schema_anchor",
    )
    g.add((anchor_bn, CAND.rank, Literal(1, datatype=XSD.integer)))
    g.add((anchor_bn, CAND.isBest, Literal(True, datatype=XSD.boolean)))

    # Materialize all unique prefixes so the graph explicitly contains
    # 0-hop, 1-hop, ..., N-hop schema candidates.
    all_paths: set[tuple[tuple[str, str], ...]] = {()}
    for path_sig in sampled:
        upto = min(depth, len(path_sig))
        for hop in range(1, upto + 1):
            all_paths.add(tuple(path_sig[:hop]))

    ordered_paths = sorted(
        all_paths,
        key=lambda p: (len(p), -_score_schema_path(text, p), _format_schema_path(p)),
    )
    path_nodes: dict[tuple[tuple[str, str], ...], BNode] = {(): anchor_bn}

    for rank, path_sig in enumerate(ordered_paths[1:], start=1):
        path_score = float(_score_schema_path(text, path_sig))
        parent_sig = tuple(path_sig[:-1])
        parent_bn = path_nodes.get(parent_sig, anchor_bn)
        step_dir, step_rel = path_sig[-1]
        step_prop = URIRef(f"http://metaqa.org/relation/{step_rel}")

        bn = _add_beam_node(
            g,
            mention=_format_schema_path(path_sig),
            depth=len(path_sig),
            score=path_score,
            parent=parent_bn,
            entity_iri=None,
            label=_format_schema_path(path_sig),
            reason="schema_path",
        )
        g.add((bn, RDF.type, CAND.SchemaPath))
        g.add((bn, CAND.viaDirection, Literal(step_dir)))
        g.add((bn, CAND.viaProperty, step_prop))
        g.add((bn, CAND.rank, Literal(rank, datatype=XSD.integer)))
        g.add((bn, CAND.pathSignature, Literal(_format_schema_path(path_sig))))
        g.add((bn, CAND.hopCount, Literal(len(path_sig), datatype=XSD.integer)))
        g.add((bn, CAND.schemaScore, Literal(round(path_score, 6), datatype=XSD.decimal)))
        g.add((meta, CAND.schemaPath, bn))
        path_nodes[path_sig] = bn

    logger.info(
        "[BEAM_DFS_SCHEMA_LOCAL] done — graph %s with %d schema paths (sampled_paths=%d)",
        g_uri,
        max(0, len(ordered_paths) - 1),
        len(sampled),
    )
    return g_uri


# ── Think-on-Graph (ToG) implementation ─────────────────────────────────────


def _tog_build_path_so_far(node: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Walk parent_ref chain to reconstruct the traversal path to this node.

    Returns a list of (entity_label, direction, relation_slug) steps,
    from the anchor down to (but not including) the current node.
    """
    steps: list[tuple[str, str, str]] = []
    cur = node
    while cur is not None:
        parent = cur.get("parent_ref")
        if parent is None:
            break
        d = cur.get("via_direction") or "out"
        prop = cur.get("via_property") or ""
        slug = _predicate_slug(URIRef(prop)) if prop else "?"
        steps.append((parent.get("label", "?"), d, slug))
        cur = parent
    steps.reverse()
    return steps


def _tog_llm_prune_relations(
    question: str,
    entity_label: str,
    relations: list[tuple[str, str]],
    top_k: int,
    path_so_far: list[tuple[str, str, str]] | None = None,
) -> list[tuple[str, str]]:
    """Relation-pruning LLM step of Think-on-Graph.

    Given the current entity, its available (direction, slug) relations,
    and the traversal path taken so far, asks the LLM to select the top-k
    relations most likely to lead toward the answer.
    Falls back to heuristic selection on LLM failure.
    """
    if not relations:
        return []
    if len(relations) <= top_k:
        return relations

    import os

    try:
        from groq import Groq
        from SPARQLLM.config import ConfigSingleton
    except ImportError:
        logger.warning("[ToG] groq not available — heuristic relation fallback")
        return relations[:top_k]

    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")

    rel_lines = "\n".join(
        f"{i}. [{d}] {slug}" for i, (d, slug) in enumerate(relations, 1)
    )
    if path_so_far:
        path_str = " → ".join(
            f"{lbl} --{d}:{slug}-->" for lbl, d, slug in path_so_far
        ) + f" {entity_label}"
    else:
        path_str = entity_label
    prompt = (
        "You are guiding a knowledge graph traversal to answer a question.\n"
        f'Question: "{question}"\n\n'
        f"Traversal so far: {path_str}\n"
        f'Current entity: "{entity_label}"\n\n'
        "Available relations (out=entity→target, in=source→entity):\n"
        f"{rel_lines}\n\n"
        f"Select up to {top_k} relation numbers (comma-separated) most likely to lead "
        "toward the answer, given the traversal context above. "
        "Output only the numbers, e.g.: 2,5,7"
    )

    try:
        client = Groq(api_key=api_key, max_retries=0)
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=64,
        )
        raw = resp.choices[0].message.content.strip()
        indices = [int(x.strip()) for x in re.findall(r"\d+", raw)]
        selected = [relations[i - 1] for i in indices if 1 <= i <= len(relations)]
        if selected:
            return selected[:top_k]
    except Exception as exc:
        logger.warning("[ToG] relation pruning LLM failed: %s", exc)

    # Heuristic fallback: prefer relation slugs matching question keywords
    hints = _question_relation_hints(question)
    scored = [(1 if slug in hints else 0, d, slug) for d, slug in relations]
    scored.sort(key=lambda x: -x[0])
    return [(d, slug) for _, d, slug in scored[:top_k]]


def _tog_llm_check_stop(
    question: str,
    beam: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Stopping-criterion LLM step of Think-on-Graph.

    Asks the LLM whether the current frontier is sufficient to answer the
    question. Returns (can_stop, tentative_answer).
    """
    if not beam:
        return False, ""

    import os

    try:
        from groq import Groq
        from SPARQLLM.config import ConfigSingleton
    except ImportError:
        return False, ""

    cfg = ConfigSingleton()
    model_name = cfg.config["Requests"].get("SLM-GROQ-MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("GROQ_API_KEY", "")

    entity_lines = "\n".join(
        "- {} (via {}:{})".format(
            c.get("label", "?"),
            c.get("via_direction", "?"),
            _predicate_slug(URIRef(c["via_property"])) if c.get("via_property") else "?",
        )
        for c in beam[:20]
    )
    prompt = (
        "You are answering a multi-hop question by traversing a knowledge graph.\n"
        f'Question: "{question}"\n\n'
        "Current candidate entities on the search frontier:\n"
        f"{entity_lines}\n\n"
        "Can you now answer the question using one or more of these candidates?\n"
        'Respond with ONLY a JSON object: {{"can_answer": true/false, "answer": "...or empty"}}'
    )

    try:
        client = Groq(api_key=api_key, max_retries=0)
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=128,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            parsed = _json.loads(m.group())
            return bool(parsed.get("can_answer", False)), str(parsed.get("answer", ""))
    except Exception as exc:
        logger.warning("[ToG] stop-check LLM failed: %s", exc)

    return False, ""


def TOG_LOCAL(
    question: Any,
    anchor: Any,
    g_source: Any,
    max_hops: Any = 2,
    beam_width: Any = 10,
    expand_k: Any = 50,
    top_k_r: Any = 5,
) -> Any:
    """Think-on-Graph (ToG) over a local MetaQA-style RDF graph.

    Faithful implementation of Sun et al. (2023) "Think-on-Graph":
      For each hop:
        a. Relation pruning  (LLM): enumerate relations from frontier → LLM keeps top-K_r
        b. Entity expansion       : follow selected relations in the local graph
        c. Entity pruning    (LLM): score entities with CBD context → keep top-K_e
        d. Stopping criterion(LLM): if LLM can answer from current frontier → stop early

    Parameters
    ----------
    question   : natural-language question
    anchor     : topic entity (label or IRI)
    g_source   : URI of local RDF graph (MetaQA KB)
    max_hops   : max hops (default 2)
    beam_width : K_e — entities kept after entity pruning (default 10)
    expand_k   : local neighbours fetched per entity (default 50)
    top_k_r    : K_r — relations kept per entity after relation pruning (default 5)
    """
    text = _to_text(question)
    src = store.get_context(g_source)
    hops = max(1, _to_int(max_hops, 2))
    keep_k = max(1, _to_int(beam_width, 10))
    ex_k = max(1, _to_int(expand_k, 50))
    kr = max(1, _to_int(top_k_r, 5))

    anchor_iri, anchor_label, anchor_name = _resolve_local_metaqa_anchor(src, anchor, text)
    if not anchor_iri:
        logger.warning("[ToG] Could not resolve anchor '%s'", anchor_name)
        g_uri = _graph_uri("tog_local", [text, str(anchor), str(g_source), "empty"])
        _new_beam_graph(g_uri, text, iteration=0)
        return g_uri

    beam: list[dict[str, Any]] = [
        {
            "entity": anchor_iri,
            "label": anchor_label,
            "score": 1.0,
            "depth": 0,
            "reason": "tog_anchor",
            "parent_ref": None,
            "via_property": None,
            "via_direction": None,
            "from_label": "",
            "relevant_facts": _collect_relevant_entity_facts(src, anchor_iri, text),
        }
    ]

    for hop in range(1, hops + 1):
        # ── Think-on-Graph (ToG) implementation ─────────────────────────────────────

        # ── (a) Relation pruning ─────────────────────────────────────────────
        selected_rels_per_entity: dict[str, list[tuple[str, str]]] = {}
        for parent in beam:
            iri = parent.get("entity", "")
            if not iri:
                continue
            exps = _expand_local_metaqa(src, iri, ex_k)
            seen_sig: set[tuple[str, str]] = set()
            rel_list: list[tuple[str, str]] = []
            for exp in exps:
                sig = (exp.get("direction", "out"), _predicate_slug(URIRef(exp.get("prop", ""))))
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    rel_list.append(sig)

            path_so_far = _tog_build_path_so_far(parent)
            pruned = _tog_llm_prune_relations(text, parent.get("label", iri), rel_list, kr, path_so_far)
            selected_rels_per_entity[iri] = pruned
            logger.info(
                "[ToG] hop %d  entity=%-30s  relations kept %d/%d: %s",
                hop,
                parent.get("label", iri),
                len(pruned),
                len(rel_list),
                [f"{d}:{s}" for d, s in pruned],
            )

        # ── (b) Entity expansion along selected relations ────────────────────
        candidates: dict[str, dict[str, Any]] = {}
        for parent in beam:
            iri = parent.get("entity", "")
            if not iri:
                continue
            wanted = set(selected_rels_per_entity.get(iri, []))
            if not wanted:
                continue
            for exp in _expand_local_metaqa(src, iri, ex_k):
                ent = exp.get("entity", "")
                if not ent or ent == anchor_iri:
                    continue
                sig = (exp.get("direction", "out"), _predicate_slug(URIRef(exp.get("prop", ""))))
                if sig not in wanted:
                    continue
                if ent in candidates:
                    continue
                candidates[ent] = {
                    "entity": ent,
                    "label": exp.get("label", ""),
                    "depth": int(parent.get("depth", 0)) + 1,
                    "parent_ref": parent,
                    "from_label": parent.get("label", ""),
                    "via_property": exp.get("prop"),
                    "via_direction": exp.get("direction"),
                    "reason": f"tog_hop{hop}:{exp.get('prop', '')}",
                    "relevant_facts": _collect_relevant_entity_facts(src, ent, text),
                }

        if not candidates:
            logger.warning("[ToG] hop %d: no candidates after relation-constrained expansion", hop)
            break

        # ── (c) Entity pruning (LLM with CBD) ────────────────────────────────
        cand_list = list(candidates.values())
        for c in cand_list:
            cbd = _build_cbd(src, c["entity"], depth=1)
            cbd_summary = _summarize_cbd_to_text(cbd)
            facts = c.get("relevant_facts", [])
            if facts:
                facts_txt = "; ".join(str(x) for x in facts[:8])
                c["cbd_summary"] = f"{cbd_summary} | relevant_facts: {facts_txt}"
            else:
                c["cbd_summary"] = cbd_summary

        llm_scores = _llm_score_candidates_with_cbd(text, cand_list)
        scored: list[dict[str, Any]] = []
        for c in cand_list:
            s = float(llm_scores.get(c["entity"], 0.0))
            if s <= 0.0:
                continue
            c["score"] = s
            scored.append(c)

        if not scored:
            logger.warning("[ToG] hop %d: no entities survived entity pruning", hop)
            break

        scored.sort(key=lambda x: x["score"], reverse=True)
        beam = scored[:keep_k]

        logger.info(
            "[ToG] hop %d/%d: %d candidates → kept %d (best: %s  score=%.3f)",
            hop,
            hops,
            len(cand_list),
            len(beam),
            beam[0]["label"],
            beam[0]["score"],
        )

        # ── (d) Stopping criterion ────────────────────────────────────────────
        can_stop, tentative = _tog_llm_check_stop(text, beam)
        if can_stop:
            logger.info("[ToG] hop %d: stopping criterion met — tentative answer: %s", hop, tentative)
            for b in beam:
                b["reason"] = b.get("reason", "") + f"|tog_stop_hop{hop}"
            break

    # ── Materialise results ──────────────────────────────────────────────────
    g_uri = _graph_uri(
        "tog_local",
        [text, str(anchor), str(g_source), anchor_name or "", str(hops), str(keep_k), str(ex_k)],
    )
    g = _new_beam_graph(g_uri, text, iteration=hops)
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
        for fact in node_dict.get("relevant_facts", []) or []:
            g.add((bn, CAND.relevantFact, Literal(str(fact))))
        emitted[key] = bn
        return bn

    if not beam:
        fallback = {
            "entity": anchor_iri, "label": anchor_label, "score": 0.0, "depth": 0,
            "reason": "tog_anchor_fallback", "parent_ref": None,
            "via_property": None, "via_direction": None,
            "relevant_facts": _collect_relevant_entity_facts(src, anchor_iri, text),
        }
        bn = _emit(fallback)
        g.add((bn, CAND.rank, Literal(1, datatype=XSD.integer)))
        g.add((bn, CAND.isBest, Literal(True, datatype=XSD.boolean)))
        g.add((bn, CAND.isLeaf, Literal(True, datatype=XSD.boolean)))
    else:
        for rank, node in enumerate(beam, start=1):
            bn = _emit(node)
            g.add((bn, CAND.rank, Literal(rank, datatype=XSD.integer)))
            g.add((bn, CAND.isLeaf, Literal(True, datatype=XSD.boolean)))
            if rank == 1:
                g.add((bn, CAND.isBest, Literal(True, datatype=XSD.boolean)))

    logger.info("[ToG] done — graph %s  leaves=%d", g_uri, len(beam))
    return g_uri
