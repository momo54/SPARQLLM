# -*- coding: utf-8 -*-
"""MCP provider for Concise Bounded Description (CBD-like) on Wikidata.

Exposes tool `cdb.describeCBD` that returns a JSON-LD graph for a given entity IRI.
"""
from __future__ import annotations
import logging
from typing import Dict, Any

import requests

logger = logging.getLogger(__name__)


class CDBProvider:
    def __init__(self, session: requests.sessions.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "SPARQLLM/0.1 (CBD provider; mailto:you@example.org)",
        })
        self.endpoint = "https://query.wikidata.org/sparql"

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "cdb.describeCBD",
                "description": "Return a CBD-like JSON-LD for a Wikidata entity.",
                "inputs": ["entity", "language"],
            },
        ]

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "cdb.describeCBD":
            return self.tool_describe_cbd(
                entity_iri=args.get("entity", ""),
                language=args.get("language", "en"),
            )
        return {"error": f"unknown_tool {tool_name}", "media_type": "application/json"}

    def tool_describe_cbd(self, entity_iri: str, language: str = "en") -> Dict[str, Any]:
        """Return a Concise Bounded Description (CBD-like) for a Wikidata entity via WDQS.

        Constructs outgoing triples and one-hop blank nodes, plus label/description in the requested language.
        """
        if not entity_iri:
            return {"error": "missing_entity", "media_type": "application/json"}
        headers = {"Accept": "application/ld+json", "User-Agent": "SPARQLLM/0.1 (CBD)"}
        sparql = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <https://schema.org/>

        CONSTRUCT {{
          <{entity_iri}> ?p ?o .
          <{entity_iri}> rdfs:label ?lbl .
          <{entity_iri}> schema:description ?desc .
          ?o ?bp ?bo .
        }} WHERE {{
          <{entity_iri}> ?p ?o .
          OPTIONAL {{ <{entity_iri}> rdfs:label ?lbl FILTER(lang(?lbl) = "{language}") }}
          OPTIONAL {{ <{entity_iri}> schema:description ?desc FILTER(lang(?desc) = "{language}") }}
          FILTER(isBlank(?o))
          ?o ?bp ?bo .
        }}
        """
        try:
            logger.debug("[CDBProvider] WDQS CBD SPARQL: %s", sparql)
            resp = self.session.get(self.endpoint, params={"query": sparql}, headers=headers, timeout=30)
            resp.raise_for_status()
            jsonld_obj = resp.json()
            logger.debug("[CDBProvider] Retrieved CBD for %s", entity_iri)
        except Exception as e:
            logger.error("[CDBProvider] WDQS CBD error: %s", e)
            return {"error": "wdqs_failed", "message": str(e), "media_type": "application/json"}
        anchor = f"urn:wikidata:cbd:{entity_iri.rsplit('/',1)[-1]}"
        return {"media_type": "application/ld+json", "jsonld": jsonld_obj, "graph_anchor": anchor}
