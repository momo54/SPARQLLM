# -*- coding: utf-8 -*-
"""UDF: LLM_RANK_ENTITIES

Given an utterance and a graph of candidate entities (from search), call the
LLM to select the best entity per mention and return a JSON-LD graph.
"""
from __future__ import annotations

import json
from typing import Any

from rdflib import URIRef

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.llmgraph_groq import llm_graph_groq


def LLM_RANK_ENTITIES(utterance: Any, g_search: Any) -> Any:
    """Rank candidate entities for an utterance using the LLM.

    Parameters
    ----------
    utterance : RDF term, expected to be a Literal
    g_search  : RDF term, expected to be a URIRef identifying a named graph
                containing candidate entities (e.g. from wikidata.searchEntities)

    Returns
    -------
    URIRef of a named graph containing cand:ChosenEntity nodes.
    """

    print(f"LLM_RANK_ENTITIES called with utterance={utterance}, g_search={g_search}")

    if utterance is None or g_search is None:
        return None

    text_utterance = str(utterance)

    # Load candidates from the named graph g_search via the global store.
    # We expect the Wikidata search DataFeed shape:
    #   g_search schema:dataFeedElement ?item .
    #   ?item schema:position ?pos ; schema:item ?entity .
    #   ?entity rdfs:label ?label ; schema:description ?desc .
    from rdflib.namespace import RDF, RDFS
    from rdflib import Namespace

    SCHEMA = Namespace("https://schema.org/")

    named_graph = store.get_context(g_search)
    print(f"LLM_RANK_ENTITIES: loaded named_graph with {len(named_graph)} triples")
    try:
      turtle_str = named_graph.serialize(format="turtle")
      if isinstance(turtle_str, bytes):
        turtle_str = turtle_str.decode("utf-8")
      print(f"LLM_RANK_ENTITIES: named_graph = {turtle_str}")
    except Exception as e:
      print(f"LLM_RANK_ENTITIES: error serializing named_graph to Turtle: {e}")

    # Interroger explicitement le graphe de recherche pour extraire
    # position, entité, label et description des candidats.
    from rdflib.plugins.sparql import prepareQuery

    q = prepareQuery(
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
        """
    )

    results = named_graph.query(q)

    candidates_lines: list[str] = []
    for row in results:
        pos = str(row.pos)
        entity = row.entity
        label = str(row.label)
        desc = str(row.desc)
        candidates_lines.append(
            f"- [{pos}] {label} ({str(entity)}) -- {desc}".strip()
        )

    candidates_block = "\n".join(candidates_lines) if candidates_lines else "(no candidates found)"
    if candidates_block == "(no candidates found)":
        print("LLM_RANK_ENTITIES: no candidates found in g_search")
        return None

    prompt = f"""You are an entity linking assistant.

Utterance:
{text_utterance}

Candidate entities (from a previous search step):
{candidates_block}

For this utterance, choose the single best entity for each mention
from the candidate list above.

Return ONLY a JSON-LD document using the following schema:

- Use namespace cand: http://example.org/cand#
- Return one or more objects of type cand:ChosenEntity with:
  - cand:mentionText : the text span of the mention (string)
  - cand:entity      : the IRI of the chosen entity (string, full IRI)
  - cand:label       : a human-readable label for the chosen entity (string)

Example JSON-LD shape:
{{
  "@context": {{ "cand": "http://example.org/cand#" }},
  "@graph": [
    {{
      "@type": "cand:ChosenEntity",
      "cand:mentionText": "Hilton in Paris",
      "cand:entity": "http://www.wikidata.org/entity/Q90",
      "cand:label": "Paris"
    }}
  ]
}}
"""

    # Call the existing JSON-LD LLM helper.
    print(f"LLM_RANK_ENTITIES prompt: {prompt[50:]} !!!")
    g_rank = llm_graph_groq(prompt)
#    print(f"LLM_RANK_ENTITIES: g_rank = {g_rank}")
    return g_rank
