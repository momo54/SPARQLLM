# -*- coding: utf-8 -*-
"""MCP provider for Entity Reranking tasks.

Exposes a tool `entity.rerank` that takes an utterance and a candidate graph URI,
and returns a JSON-LD graph of reranked entities.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List

from rdflib import URIRef, Namespace, BNode
from rdflib.namespace import RDF, RDFS, SKOS
from rdflib.plugins.sparql import prepareQuery

from SPARQLLM.udf.SPARQLLM import store

logger = logging.getLogger(__name__)
SCHEMA = Namespace("https://schema.org/")

class RerankProvider:
    """Provider for Entity Reranking tasks."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        # Default model
        self.model = self.config.get('Requests', {}).get('SLM-GROQ-MODEL', 'llama-3.3-70b-versatile')
        
        # Initialize Groq client
        try:
            from groq import Groq
            # Try to get API key from config or env (Groq client handles env GROQ_API_KEY automatically)
            api_key = self.config.get('ApiKeys', {}).get('GROQ_API_KEY')
            self.client = Groq(api_key=api_key)
        except ImportError:
            self.client = None
            logger.warning("groq package not installed, RerankProvider will fail.")
        except Exception as e:
            self.client = None
            logger.warning(f"Failed to initialize Groq client: {e}")

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "entity.rerank":
            return self.tool_rerank(args)
        return {"error": f"Unknown tool: {tool_name}"}

    def tool_rerank(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Args:
            utterance: str
            candidates_graph_uri: str (URI of the named graph containing candidates)
        """
        utterance = args.get("utterance")
        g_uri_str = args.get("candidates_graph_uri")

        if not utterance or not g_uri_str:
            return {"error": "Missing utterance or candidates_graph_uri"}

        if not self.client:
            return {"error": "Groq client not initialized"}

        # 1. Extract candidates from the RDF store
        try:
            # Handle BNode IDs (if string doesn't look like a URI)
            if g_uri_str.startswith("http") or g_uri_str.startswith("urn:"):
                g_node = URIRef(g_uri_str)
            else:
                g_node = BNode(g_uri_str)

            candidates = self._extract_candidates(g_node)
        except Exception as e:
            return {"error": f"Failed to extract candidates: {e}"}
        
        if not candidates:
            # Return empty graph if no candidates
            logger.warning(f"No candidates found in graph {g_uri_str}")
            return {
                "jsonld": {
                    "@context": {
                        "cand": "http://example.org/cand#",
                        "xsd": "http://www.w3.org/2001/XMLSchema#"
                    },
                    "@graph": []
                },
                "media_type": "application/ld+json"
            }

        # 2. Build prompt
        prompt = self._build_prompt(utterance, candidates)

        # 3. Call LLM
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            response_content = completion.choices[0].message.content
            json_response = json.loads(response_content)
            
            # Normalize JSON-LD structure
            if "@graph" not in json_response and isinstance(json_response, list):
                 json_response = {"@graph": json_response}
            
            if "@context" not in json_response:
                json_response["@context"] = {
                    "cand": "http://example.org/cand#",
                    "xsd": "http://www.w3.org/2001/XMLSchema#"
                }

            return {
                "jsonld": json_response,
                "media_type": "application/ld+json"
            }

        except Exception as e:
            logger.error(f"Rerank LLM call failed: {e}")
            return {"error": str(e)}

    def _extract_candidates(self, graph_node: Any) -> List[Dict]:
        """Read the candidate graph and return ordered candidate dicts."""
        named_graph = store.get_context(graph_node)
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
        candidates = []
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

    def _build_prompt(self, utterance: str, candidates: List[Dict]) -> str:
        candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
        return f"""You are an assistant that re-ranks Wikidata candidates for entity linking.

Utterance:
{utterance}

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
- cand:rank (integer, 1-based)
- cand:confidence (float 0.0-1.0)
- cand:reason (short explanation string)

Output JSON-LD format ONLY.
"""
