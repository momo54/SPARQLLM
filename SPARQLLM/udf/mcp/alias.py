# -*- coding: utf-8 -*-
"""SPARQL alias/wrapper functions around MCP tools.

Each function registers a custom SPARQL function (e.g. ggf:LLM) that internally
invokes the generic `slm_mcp_tool` to avoid verbose OBJECT construction in queries.

Add new aliases here instead of polluting slm_mcp_tool.py.
"""
from __future__ import annotations
import json
import logging
from rdflib import Namespace
from rdflib.plugins.sparql.operators import register_custom_function

# Lazy references populated on first call to avoid import errors if optional providers missing
_slm_loaded = False
slm_mcp_tool = None
_cfg = None
default_groq_model = None

logger = logging.getLogger(__name__)
GGF = Namespace("http://ggf.org/")


def _alias_llm(prompt_term, model_term="llama-3.3-70b-versatile", temp_term=None):
    """ggf:LLM(prompt, model [, temperature]) -> graph node (BNode or URIRef)

    Parameters are rdflib terms; they are cast to strings. Temperature optional.
    """
    global _slm_loaded, slm_mcp_tool, _cfg, default_groq_model
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _cfg = _slm_mod._cfg
            default_groq_model = _slm_mod.default_groq_model
            _slm_loaded = True
        if prompt_term is None:
            return None
        prompt = str(prompt_term)
        model = str(model_term) if model_term is not None else _cfg.config['Requests'].get('SLM-GROQ-MODEL', default_groq_model)
        temperature = 0.0
        if temp_term is not None:
            try:
                temperature = float(str(temp_term))
            except Exception:
                temperature = 0.0
        args = {
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
        }
        return slm_mcp_tool("groq", "groq.generate_jsonld", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:LLM] error: {e}")
        return None

# Register
#register_custom_function(GGF.LLM, _alias_llm)


def _alias_snapshot(url_term, text_max_term=None):
    """ggf:SNAP(url [, text_max]) -> graph node for browser snapshot

    Paramètres:
      url: IRI ou littéral string
      text_max (optionnel): taille max du texte (défaut 3000)
    Utilise des valeurs par défaut fixées (wait_ms=500, snippet_only=true, redact_pi=true).
    """
    global _slm_loaded, slm_mcp_tool, _cfg
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _cfg = _slm_mod._cfg
            _slm_loaded = True
        if url_term is None:
            return None
        url = str(url_term)
        text_max = 3000
        if text_max_term is not None:
            try:
                text_max = int(str(text_max_term))
            except Exception:
                text_max = 3000
        args = {
            "url": url,
            "wait_ms": 500,
            "text_max": text_max,
            "snippet_only": True,
            "redact_pi": True,
        }
        return slm_mcp_tool("browser", "browser.snapshot", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:SNAP] error: {e}")
        return None

# Enregistrement de l'alias snapshot (nom unique, pas de collision connue)
#register_custom_function(GGF.SNAP, _alias_snapshot)


def _alias_ddg_search(query_term, limit_term=None, region_term=None, safesearch_term=None):
    """ggf:SEARCH(query [, limit [, region [, safesearch]]]) -> graph node for DuckDuckGo search

    Paramètres (tous rdflib terms):
      query: texte de recherche
      limit (optionnel, défaut 3)
      region (optionnel, défaut "us-en")
      safesearch (optionnel, défaut "moderate")
    """
    global _slm_loaded, slm_mcp_tool, _cfg
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _cfg = _slm_mod._cfg
            _slm_loaded = True
        if query_term is None:
            return None
        query = str(query_term)
        # Valeurs par défaut alignées avec la requête actuelle
        limit = 3
        if limit_term is not None:
            try:
                limit = int(str(limit_term))
            except Exception:
                limit = 3
        region = str(region_term) if region_term is not None else "us-en"
        safesearch = str(safesearch_term) if safesearch_term is not None else "moderate"
        args = {
            "query": query,
            "limit": limit,
            "region": region,
            "safesearch": safesearch,
        }
        return slm_mcp_tool("duckduckgo", "duckduckgo.search", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:SEARCH] error: {e}")
        return None

def _alias_wikidata_search(search_term, lang_term=None, limit_term=None):
    """ggf:WIKIDATA-SEARCH-ENTITY(search [, lang [, limit]]) -> graph node

    search: texte de recherche (obligatoire)
    lang: code de langue (optionnel, défaut "en")
    limit: nombre max de résultats (optionnel, défaut 10)
    """
    global _slm_loaded, slm_mcp_tool, _cfg
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _cfg = _slm_mod._cfg
            _slm_loaded = True
        if search_term is None:
            return None
        search = str(search_term)
        lang = str(lang_term) if lang_term is not None and str(lang_term) != "" else "en"
        try:
            limit = int(str(limit_term)) if limit_term is not None else 10
        except Exception:
            limit = 10
        args = {
            "search": search,
            "language": lang,
            "limit": limit,
        }
        return slm_mcp_tool("wikidata", "wikidata.searchEntities", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:WIKIDATA-SEARCH-ENTITY] error: {e}")
        return None

def _alias_wikidata_cbd(entity_term, lang_term=None):
    """ggf:WIKIDATA-CBD(entity [, lang]) -> graph node

    Parameters are rdflib terms; they are cast to strings.
    """
    global _slm_loaded, slm_mcp_tool
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _slm_loaded = True
        if entity_term is None:
            return None
        entity = str(entity_term)
        lang = str(lang_term) if lang_term is not None and str(lang_term) != "" else "en"
        args = {"entity": entity, "language": lang}
        return slm_mcp_tool("wikidata", "wikidata.describeCBD", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:WIKIDATA-CBD] error: {e}")
        return None

def _alias_cdb_cbd(entity_term, lang_term=None):
    """ggf:WIKIDATA-CBD-CDB(entity [, lang]) -> graph node via CDB provider"""
    global _slm_loaded, slm_mcp_tool
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _slm_loaded = True
        if entity_term is None:
            return None
        entity = str(entity_term)
        lang = str(lang_term) if lang_term is not None and str(lang_term) != "" else "en"
        args = {"entity": entity, "language": lang}
        return slm_mcp_tool("cdb", "cdb.describeCBD", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:WIKIDATA-CBD-CDB] error: {e}")
        return None


def _alias_rerank_entities_mcp(query_term, candidates_graph_term):
    """ggf:LLM-RERANK-ENTITIES-MCP(query, candidates_graph) -> graph node

    candidates_graph_term: URI of the graph containing candidates (e.g. from WIKIDATA-SEARCH-ENTITY).
    """
    global _slm_loaded, slm_mcp_tool
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _slm_loaded = True
        
        if query_term is None or candidates_graph_term is None:
            return None
            
        query = str(query_term)
        graph_uri = str(candidates_graph_term)
        
        args = {
            "utterance": query,
            "candidates_graph_uri": graph_uri
        }
        
        return slm_mcp_tool("entity", "entity.rerank", args)
    except Exception as e:
        logger.error(f"[alias ggf:LLM-RERANK-ENTITIES-MCP] error: {e}")
        return None

def _alias_summarize_rdf_ttl(graph_term, entity_term, prompt_template_term=None):
    """ggf:SUMMARIZE-RDF-TTL(graph, entityIRI [, prompt_template]) -> graph node (BNode or URIRef)
    """
    global _slm_loaded, slm_mcp_tool, _cfg
    try:
        if not _slm_loaded:
            from SPARQLLM.udf.mcp import slm_mcp_tool as _slm_mod
            slm_mcp_tool = _slm_mod.slm_mcp_tool
            _cfg = _slm_mod._cfg
            _slm_loaded = True
        if graph_term is None or entity_term is None:
            return None
        graph_uri = str(graph_term)
        entity_iri = str(entity_term)
        args = {
            "graph_uri": graph_uri,
            "entity_iri": entity_iri,
        }
        if prompt_template_term is not None:
            args["prompt_template"] = str(prompt_template_term)
        return slm_mcp_tool("summarize_rdf", "summarize_rdf_ttl", json.dumps(args))
    except Exception as e:
        logger.error(f"[alias ggf:SUMMARIZE-RDF-TTL] error: {e}")
        return None

# Enregistrement de l'alias
#register_custom_function(GGF["SUMMARIZE-RDF-TTL"], _alias_summarize_rdf_ttl)

"""Ce module définit les fonctions alias GGF.

L'enregistrement auprès de rdflib (register_custom_function) est géré
par la config (voir `config.ini` et `ConfigSingleton`).
"""

