# -*- coding: utf-8 -*-
"""
Provider MCP pour la summarisation d'un graphe RDF centré sur une entité (CBD/ego-net).
Sérialise le graphe en Turtle et appelle un LLM avec un prompt pour obtenir un résumé.
"""
from typing import Dict, Any
from rdflib import URIRef, BNode
from SPARQLLM.udf.SPARQLLM import store
import logging

logger = logging.getLogger(__name__)

DEFAULT_PROMPT = """You are given an RDF graph in Turtle syntax describing a person and related entities.\n\nEach triple is of the form: subject predicate object.\n\nRDF graph:\n<graph>\n{ttl}\n</graph>\n\nTask:\nWrite a short, fluent English description (2–3 sentences) about this person. Mention their name, profession and affiliation."""

class SummarizeRDFProvider:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        try:
            from groq import Groq
            api_key = self.config.get('ApiKeys', {}).get('GROQ_API_KEY')
            self.client = Groq(api_key=api_key)
        except ImportError:
            self.client = None
            logger.warning("groq package not installed, SummarizeRDFProvider will fail.")
        except Exception as e:
            self.client = None
            logger.warning(f"Failed to initialize Groq client: {e}")

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "summarize_rdf_ttl":
            return self.tool_summarize_rdf_ttl(args)
        return {"error": f"Unknown tool: {tool_name}"}

    def tool_summarize_rdf_ttl(self, args: Dict[str, Any]) -> Dict[str, Any]:
        graph_uri = args.get("graph_uri")
        entity_iri = args.get("entity_iri")
        prompt_template = args.get("prompt_template") or DEFAULT_PROMPT
        if not graph_uri or not entity_iri:
            return {"error": "Missing graph_uri or entity_iri"}
        if not self.client:
            return {"error": "Groq client not initialized"}
        # 1. Extraire le sous-graphe centré sur l'entité (CBD/ego-net)
        g = store.get_context(URIRef(graph_uri) if graph_uri.startswith("http") or graph_uri.startswith("urn:") else BNode(graph_uri))
        # Pour l'exemple, on sérialise tout le graphe (à adapter pour extraire CBD si besoin)
        ttl = g.serialize(format="turtle")
        # 2. Construire le prompt
        prompt = prompt_template.replace("{ttl}", ttl)
        # 3. Appeler le LLM
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.config.get('Requests', {}).get('SLM-GROQ-MODEL', 'llama-3.3-70b-versatile'),
                temperature=0.0,
                response_format={"type": "text"}
            )
            summary = completion.choices[0].message.content.strip()
            # Construction du JSON-LD
            jsonld = {
                "@context": "https://schema.org/",
                "@type": "Person",
                "schema:description": summary,
                "schema:entity": entity_iri
            }
            logger.debug("Summarize LLM response: %s", summary)
            return {
                "jsonld": jsonld,
                "prompt": prompt,
                "media_type": "application/ld+json"
            }
        except Exception as e:
            logger.error(f"Summarize LLM call failed: {e}")
            return {"error": str(e)}

# Singleton pour le broker
_summarize_rdf_provider_singleton = None
def get_summarize_rdf_provider():
    global _summarize_rdf_provider_singleton
    if _summarize_rdf_provider_singleton is None:
        _summarize_rdf_provider_singleton = SummarizeRDFProvider()
    return _summarize_rdf_provider_singleton
