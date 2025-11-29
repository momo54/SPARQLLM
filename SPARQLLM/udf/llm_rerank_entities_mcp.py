# -*- coding: utf-8 -*-
"""UDF: LLM_RERANK_ENTITIES_MCP

Rerank all candidate entities using the Groq JSON-LD MCP tool. Unlike the legacy
LLM_RANK_ENTITIES helper, this function produces an ordered list covering every
candidate and relies on the generic slm_mcp_tool plumbing for provenance.
"""
from __future__ import annotations

import json
from typing import Any, List, Dict

from rdflib import Namespace
from rdflib.plugins.sparql import prepareQuery

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod

# Reuse the configured MCP helpers
slm_mcp_tool = _slm_mod.slm_mcp_tool
_cfg = _slm_mod._cfg
_default_groq_model = _slm_mod.default_groq_model

SCHEMA = Namespace("https://schema.org/")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")


def _extract_candidates(g_search: Any) -> List[Dict[str, str]]:
    """Read the candidate graph and return ordered candidate dicts."""
    named_graph = store.get_context(g_search)
    query = prepareQuery(
        """
        PREFIX schema: <https://schema.org/>
        PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?pos ?entity ?label ?desc
        WHERE {
          ?item a schema:DataFeedItem ;
                schema:position ?pos ;
                schema:item ?entity .
          ?entity rdfs:label ?label ;
                  schema:description ?desc .
        }
        ORDER BY ?pos
        """
    )
    results = named_graph.query(query)
    candidates: List[Dict[str, str]] = []
    for row in results:
        try:
            pos_val = int(str(row.pos))
        except Exception:
            pos_val = None
        candidates.append(
            {
                "position": pos_val,
                "entity": str(row.entity),
                "label": str(row.label),
                "description": str(row.desc),
            }
        )
    candidates.sort(key=lambda x: (x["position"] is None, x["position"]))
    return candidates


def LLM_RERANK_ENTITIES_MCP(utterance: Any, g_search: Any, temperature: Any = None) -> Any:
    """Return a named graph containing cand:RerankedEntity nodes for every candidate."""
    if utterance is None or g_search is None:
        return None

    text_utterance = str(utterance)
    temp_value = 0.0
    if temperature is not None:
        try:
            temp_value = float(str(temperature))
        except Exception:
            temp_value = 0.0

    candidates = _extract_candidates(g_search)
    if not candidates:
        print("LLM_RERANK_ENTITIES_MCP: no candidates found")
        return None

    candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
    prompt = f"""You are an assistant that re-ranks Wikidata candidates for entity linking.

Utterance:
{text_utterance}

Candidates (JSON array, preserve the items but reorder them best-first):
{candidates_json}

Produce a JSON-LD document that lists every candidate exactly once, ordered by
preference for answering the utterance. Use the cand: namespace
(http://example.org/cand#) and emit one cand:RerankedEntity per candidate with
these fields:
- cand:entity (IRI string)
- cand:label (string)
- cand:description (string)
- cand:originalPosition (integer from the input)
- cand:rank (integer starting at 1, where 1 is best)
- cand:confidence (float between 0 and 1)
- cand:reason (short justification string)

The @context must include: "cand": "http://example.org/cand#".

Ensure the @graph array contains all candidates and nothing else.
"""

    try:
        model = _cfg.config['Requests'].get('SLM-GROQ-MODEL', _default_groq_model)
    except Exception:
        model = _default_groq_model

    args = {
        "prompt": prompt,
        "model": model,
        "temperature": temp_value,
    }

    try:
        graph_uri = slm_mcp_tool("groq", "groq.generate_jsonld", json.dumps(args, ensure_ascii=False))
        return graph_uri
    except Exception as exc:
        print(f"LLM_RERANK_ENTITIES_MCP error: {exc}")
        return None
