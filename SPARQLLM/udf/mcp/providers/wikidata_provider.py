# -*- coding: utf-8 -*-
"""MCP provider for Wikidata searchEntities API.

Exposes a tool `wikidata.searchEntities` returning JSON-LD describing search hits.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Dict, Any

import requests

logger = logging.getLogger(__name__)


class WikidataProvider:
    API_URL = "https://www.wikidata.org/w/api.php"

    def __init__(self, session: requests.sessions.Session | None = None) -> None:
        # Utiliser une session dédiée avec un User-Agent explicite, comme
        # recommandé par Wikimedia pour les appels programmatiques.
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "SPARQLLM/0.1 (Wikidata entity search; mailto:you@example.org)",
            }
        )

    def tool_search_entities(self, search: str, language: str = "en", limit: int = 10) -> Dict[str, Any]:
        """Call Wikidata wbsearchentities and wrap result as JSON-LD.

        Parameters
        ----------
        search: search text
        language: language code (e.g. "en")
        limit: maximum number of results
        """
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "search": search,
            "language": language or "en",
            "limit": int(limit) if limit is not None else 10,
        }
        logger.debug("[WikidataProvider] searchEntities params=%s", params)
        try:
            resp = self.session.get(self.API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("[WikidataProvider] error calling wbsearchentities: %s", e)
            return {"error": str(e), "media_type": "application/json"}

        now = datetime.now(timezone.utc).isoformat()
        hits = []
        for idx, item in enumerate(data.get("search", []), start=1):
            qid = item.get("id")
            if not qid:
                continue
            ent_iri = f"http://www.wikidata.org/entity/{qid}"
            hit = {
                "@id": ent_iri,
                "@type": "schema:Thing",
                "schema:position": idx,
            }
            if item.get("label"):
                hit["rdfs:label"] = {
                    "@value": item["label"],
                    "@language": language or "en",
                }
            if item.get("description"):
                hit["schema:description"] = {
                    "@value": item["description"],
                    "@language": language or "en",
                }
            hits.append(hit)

        # Encodage de la valeur de recherche pour construire un @id sans espaces,
        # afin d'éviter les problèmes de parsing JSON-LD côté rdflib.
        from urllib.parse import quote
        safe_search = quote(search, safe="")

        jsonld = {
            "@context": {
                "schema": "https://schema.org/",
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            },
            "@id": f"urn:wikidata:search:{safe_search}",
            "@type": "schema:DataFeed",
            "schema:name": f"Wikidata search results for {search}",
            "schema:query": search,
            "schema:dateCreated": now,
            "schema:dataFeedElement": [
                {
                    "@type": "schema:DataFeedItem",
                    "schema:position": h.get("schema:position"),
                    "schema:item": {
                        k: v for k, v in h.items() if k not in {"schema:position"}
                    },
                }
                for h in hits
            ],
        }

        return {
            "media_type": "application/ld+json",
            "jsonld": jsonld,
            "graph_anchor": jsonld["@id"],
        }

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "wikidata.searchEntities",
                "description": "Search Wikidata entities by label/description.",
                "inputs": ["search", "language", "limit"],
            }
        ]

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "wikidata.searchEntities":
            return self.tool_search_entities(
                search=args.get("search", ""),
                language=args.get("language", "en"),
                limit=args.get("limit", 10),
            )
        return {"error": f"unknown_tool {tool_name}", "media_type": "application/json"}
