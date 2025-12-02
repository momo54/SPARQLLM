# SPARQLLM/udf/mcp/slm_mcp_tool.py
# -*- coding: utf-8 -*-

import json, hashlib, traceback, logging
from typing import Union, Dict, Any, List

from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD
from rdflib import ConjunctiveGraph, Graph, URIRef,BNode

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists

from SPARQLLM.udf.mcp.client import MCPClient
from SPARQLLM.udf.mcp.providers.github_provider import get_provider
from SPARQLLM.udf.mcp.providers.postgres_provider import get_pg_provider
from SPARQLLM.udf.mcp.providers.duckduckgo_provider import get_duckduckgo_provider
from SPARQLLM.udf.mcp.providers.browser_provider import get_browser_provider
from SPARQLLM.udf.mcp.providers.faiss_provider import get_provider as get_faiss_provider
from SPARQLLM.udf.mcp.providers.rerank_provider import RerankProvider
from SPARQLLM.udf.mcp.providers.cdb_provider import CDBProvider
from SPARQLLM.udf.mcp.providers.summarize_rdf_provider import get_summarize_rdf_provider
from SPARQLLM.udf.llmgraph_groq import llm_graph_groq_model, model as default_groq_model
from SPARQLLM.config import ConfigSingleton


logger = logging.getLogger(__name__)

# --- MCP client (adapter) ---
# Tu peux brancher ici ton client HTTP/STDIO ; il suffit d'implémenter tools_call(handle, tool, args)
# Exemple : from SPARQLLM.udf.mcp.client import MCPClient ; _MCP = MCPClient()
#_MCP = None  # à injecter au démarrage (voir en bas)
_MCP = MCPClient()

import os
gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT")

# Option 1 : handle HTTP générique (si un jour un vrai serveur MCP GitHub est dispo)
# if gh_token:
#     _MCP.connect_http("github-http", "https://api.github.com", f"Bearer {gh_token}")

# Option 2 : handle statique + tool spécialisé GitHub PRs
_MCP.connect_static("github")

_provider = get_provider()
_pg_provider = get_pg_provider()
_ddg_provider = get_duckduckgo_provider()
_browser = get_browser_provider()
_faiss_provider = get_faiss_provider()
from SPARQLLM.udf.mcp.providers.wikidata_provider import WikidataProvider
_wikidata_provider = WikidataProvider()
_rerank_provider = RerankProvider()
_cdb_provider = CDBProvider()
_summarize_rdf_provider = get_summarize_rdf_provider()
# Summarize RDF tool
_MCP.connect_static("summarize_rdf")
_MCP.register_static_tool("summarize_rdf", "summarize_rdf_ttl", lambda a: _summarize_rdf_provider.call("summarize_rdf_ttl", a))

# GROQ model config singleton (reuse existing config if needed)
_cfg = ConfigSingleton()


def _tool_dispatch(tool_args: dict, tool_name: str):
    return _provider.call(tool_name, tool_args)

_MCP.register_static_tool("github", "github.pullRequests.list", lambda a: _tool_dispatch(a, "github.pullRequests.list"))
_MCP.register_static_tool("github", "github.issues.list", lambda a: _tool_dispatch(a, "github.issues.list"))
_MCP.connect_static("postgres")
_MCP.register_static_tool("postgres", "postgres.tables.list", lambda a: _pg_provider.call("postgres.tables.list", a))
_MCP.register_static_tool("postgres", "postgres.table.preview", lambda a: _pg_provider.call("postgres.table.preview", a))
_MCP.register_static_tool("postgres", "postgres.sql.query", lambda a: _pg_provider.call("postgres.sql.query", a))

_MCP.connect_static("duckduckgo")
_MCP.register_static_tool(
    "duckduckgo",
    "duckduckgo.search",
    lambda a: _ddg_provider.call("duckduckgo.search", a)
)

_MCP.connect_static("browser")
_MCP.register_static_tool(
    "browser",
    "browser.snapshot",
    lambda a: _browser.call("browser.snapshot", a)
)

# FAISS provider tools
_MCP.connect_static("faiss")
_MCP.register_static_tool("faiss", "faiss.index_file", lambda a: _faiss_provider.call("faiss.index_file", a))
_MCP.register_static_tool("faiss", "faiss.search_index", lambda a: _faiss_provider.call("faiss.search_index", a))

# Wikidata searchEntities tool
_MCP.connect_static("wikidata")
_MCP.register_static_tool("wikidata", "wikidata.searchEntities", lambda a: _wikidata_provider.call("wikidata.searchEntities", a))
_MCP.register_static_tool("wikidata", "wikidata.describeCBD", lambda a: _wikidata_provider.call("wikidata.describeCBD", a))

# Entity Rerank tool
_MCP.connect_static("entity")
_MCP.register_static_tool("entity", "entity.rerank", lambda a: _rerank_provider.call("entity.rerank", a))

# CDB tool
_MCP.connect_static("cdb")
_MCP.register_static_tool("cdb", "cdb.describeCBD", lambda a: _cdb_provider.call("cdb.describeCBD", a))

# GROQ tool wrapper
def _groq_generate(args: dict):
    """Call Groq LLM to generate JSON-LD and return as MCP JSON-LD contract.

        Inputs (args):
            prompt (str, required)
            uri (str, optional) -> used to derive stable graph IRI if provided
            model (str, optional) -> override default model from config
            temperature (float, optional, 0-2) -> sampling temperature (default 0)

    Returns:
      {"media_type":"application/ld+json", "jsonld": <obj>, "graph_anchor": <iri>}
    """
    import json as _json
    from rdflib import URIRef
    prompt = args.get('prompt') or ''
    if not prompt:
        return {"error": "missing_prompt", "message": "'prompt' argument is required"}
    uri = args.get('uri')
    model = args.get('model') or _cfg.config['Requests'].get('SLM-GROQ-MODEL', default_groq_model)
    temperature = args.get('temperature', 0.0)
    try:
        temperature = float(temperature)
    except Exception:
        temperature = 0.0
    try:
        graph_uri = llm_graph_groq_model(prompt, uri, model, temperature=temperature)
    except Exception as e:
        # Structured error object so JSON->JSON-LD heuristique crée des triples (schema:error, schema:message, schema:additionalType)
        return {
            "status": "error",
            "error": "groq_call_failed",
            "message": str(e),
            "model": model,
            "temperature": temperature
        }
    g = store.get_context(graph_uri)
    try:
        jsonld_str = g.serialize(format='json-ld')
        jsonld_obj = _json.loads(jsonld_str)
    except Exception as e:
        return {"error": "serialize_failed", "message": str(e)}
    return {"media_type": "application/ld+json", "jsonld": jsonld_obj, "graph_anchor": str(graph_uri)}

_MCP.connect_static("groq")
_MCP.register_static_tool("groq", "groq.generate_jsonld", lambda a: _groq_generate(a))


_MCP.connect_stdio("echo", ["python","SPARQLLM/servers/echo_mcp_server.py"])



SCHEMA = Namespace("https://schema.org/")
PROV   = Namespace("http://www.w3.org/ns/prov#")
from datetime import datetime, timezone
import time as _time

# --- mappers optionnels par tool (JSON -> JSON-LD) ---
PROFILE_MAPPERS = {}

def register_mapper(tool_name: str, fn):
    """fn: (dict|list) -> dict(JSON-LD)"""
    PROFILE_MAPPERS[tool_name] = fn

def _heuristic_json_to_jsonld(data: Union[Dict[str,Any], List[Dict[str,Any]]]) -> Dict[str,Any]:
    """Plan B: JSON -> JSON-LD minimal ; essaie de trouver une liste d'objets et des IDs."""
    def to_item(o: Dict[str,Any]):
        if not isinstance(o, dict):
            return None
        iid = o.get("html_url") or o.get("url") or o.get("id")
        it = {"@type": "Thing"}
        for k, v in o.items():
            if isinstance(v, (str, int, float, bool)) and v is not None:
                it[k] = v
        if iid:
            it["@id"] = str(iid)
        return it

    items: List[Dict[str,Any]] = []
    if isinstance(data, list):
        items = [x for x in map(to_item, data) if x]
    elif isinstance(data, dict):
        arr = next((v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
        items = [x for x in map(to_item, arr or [data]) if x]

    return {"@context": "https://schema.org/", "@graph": items}

def _jsonld_to_named_graph(jsonld_obj: Union[Dict[str,Any], str],
                           graph_name_hint: str) -> URIRef:
    """Parse JSON-LD -> Graph tmp -> copie dans named graph store -> retourne IRI."""
    if isinstance(jsonld_obj, dict):
        s = json.dumps(jsonld_obj)
    else:
        s = jsonld_obj  # string JSON-LD
    # 1) parse dans un Graph rdflib
    gtmp = Graph()
    gtmp.parse(data=s, format="json-ld")

    # 2) IRI du named graph (stable si même contenu)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    graph_uri = URIRef(graph_name_hint or f"urn:mcp:graph:{h}")

    # 3) créer/récupérer le named graph dans le store
    if named_graph_exists(store, graph_uri):
        logger.debug(f"[MCP] Graph {graph_uri} already exists")
        return graph_uri
    named_graph = store.get_context(graph_uri)

    # 4) copier les triples
    for t in gtmp:
        named_graph.add(t)

    return graph_uri

def json_to_jsonld(data):
    """
    Convert JSON data to JSON-LD format.
    """
    context = "https://schema.org/"
    jsonld_data = {
        "@context": context,
        "@graph": data
    }
    return jsonld_data


def _attach_prov(named_graph: Graph, graph_uri: URIRef, handle: str, tool_name: str, args: dict,
                 source_hint: str = None,
                 start_dt: datetime | None = None,
                 end_dt: datetime | None = None,
                 duration_s: float | None = None,
                 prompt_text: str | None = None):
    """Ajoute des triples PROV-O + métriques temps.

    - start_dt / end_dt: datetimes UTC
    - duration_s: float (secondes)
    """
    now = (end_dt or datetime.now(timezone.utc)).isoformat()
    act = BNode()
    agent = URIRef(f"urn:mcp:handle:{handle}")
    tool  = URIRef(f"urn:mcp:tool:{tool_name}")
    req   = BNode()

    # Entité = le graphe (on annote directement l'IRI du graphe nommé)
    named_graph.add((graph_uri, PROV.wasGeneratedBy, act))
    named_graph.add((graph_uri, PROV.generatedAtTime, Literal(now, datatype=XSD.dateTime)))
    if start_dt:
        named_graph.add((act, PROV.startedAtTime, Literal(start_dt.isoformat(), datatype=XSD.dateTime)))
    if end_dt:
        named_graph.add((act, PROV.endedAtTime, Literal(end_dt.isoformat(), datatype=XSD.dateTime)))
    if duration_s is not None:
        # Duration sur l'activité et sur l'entité (double annotation pratique)
        named_graph.add((act, SCHEMA.duration, Literal(round(duration_s,6), datatype=XSD.decimal)))
        named_graph.add((graph_uri, SCHEMA.duration, Literal(round(duration_s,6), datatype=XSD.decimal)))
    if source_hint:
        named_graph.add((graph_uri, PROV.wasDerivedFrom, URIRef(source_hint)))

    # Activité
    named_graph.add((act, RDF.type, PROV.Activity))
    named_graph.add((act, PROV.wasAssociatedWith, tool))
    named_graph.add((act, PROV.used, req))

    # Tool (SoftwareAgent)
    named_graph.add((tool, RDF.type, PROV.SoftwareAgent))
    named_graph.add((tool, SCHEMA.name, Literal(tool_name)))

    # Agent (le handle MCP)
    #named_graph.add((agent, RDF.type, PROV.SoftwareAgent))
    #named_graph.add((agent, SCHEMA.name, Literal(handle)))
    #named_graph.add((act, PROV.wasAssociatedWith, agent))

    # Requête (arguments)
    named_graph.add((req, RDF.type, PROV.Entity))
    named_graph.add((req, SCHEMA.name, Literal("args")))
    try:
        named_graph.add((req, PROV.value, Literal(json.dumps(args, ensure_ascii=False))))
    except Exception:
        named_graph.add((req, PROV.value, Literal(str(args))))
    # If provider returned an LLM prompt, store it on the request node for provenance
    if prompt_text:
        try:
            named_graph.add((req, URIRef("http://example.org/prompt"), Literal(prompt_text)))
        except Exception:
            # best-effort only
            pass

def slm_mcp_tool(handle: str,
                 tool_name: str,
                 args_json: str,
                 graph_name_hint: str = None) -> Union[URIRef, None]:
    """
    Appelle un serveur MCP, transforme le résultat en RDF, crée un named graph dans `store`,
    et *retourne l'IRI du graph* (comme slm_csv).

    - handle: identifiant de connexion à ton MCP (que tu gères côté client)
    - tool_name: nom du tool MCP ("github.pullRequests.list", "openlibrary.search", ...)
    - args_json: string JSON des arguments (ou dict si tu adaptes)
    - graph_name_hint: URI/URN à utiliser si tu veux forcer le nom du graphe

    Retour: URIRef (graph IRI) ou None en cas d'erreur.
    """
    logger.debug(f"[MCP] call tool={tool_name} args={args_json}")
    try:
        assert _MCP is not None, "MCP client not configured"
        args = json.loads(args_json) if isinstance(args_json, str) else args_json

        # (ré)enregistrement paresseux si handle github mais tools absents (cas import ordre)
        if handle == "github":
            try:
                handles = getattr(_MCP, "_handles", {})
                if "github" not in handles:
                    logger.debug("[MCP] handle 'github' absent -> reconnect_static")
                    _MCP.connect_static("github")
                if not _MCP.has_tool("github", "github.pullRequests.list"):
                    logger.debug("[MCP] (re)register github.pullRequests.list")
                    _MCP.register_static_tool("github", "github.pullRequests.list", lambda a: _tool_dispatch(a, "github.pullRequests.list"))
                if not _MCP.has_tool("github", "github.issues.list"):
                    logger.debug("[MCP] (re)register github.issues.list")
                    _MCP.register_static_tool("github", "github.issues.list", lambda a: _tool_dispatch(a, "github.issues.list"))
                logger.debug(f"[MCP] Handles actifs: {list(handles.keys())}")
            except Exception as re_err:
                logger.warning(f"[MCP] Echec re-registration github tools: {re_err}")
        # lazy registration for faiss as well
        if handle == "faiss":
            try:
                handles = getattr(_MCP, "_handles", {})
                if "faiss" not in handles:
                    logger.debug("[MCP] handle 'faiss' absent -> reconnect_static")
                    _MCP.connect_static("faiss")
                if not _MCP.has_tool("faiss", "faiss.index_file"):
                    logger.debug("[MCP] (re)register faiss.index_file")
                    _MCP.register_static_tool("faiss", "faiss.index_file", lambda a: _faiss_provider.call("faiss.index_file", a))
                if not _MCP.has_tool("faiss", "faiss.search_index"):
                    logger.debug("[MCP] (re)register faiss.search_index")
                    _MCP.register_static_tool("faiss", "faiss.search_index", lambda a: _faiss_provider.call("faiss.search_index", a))
            except Exception as re_err:
                logger.warning(f"[MCP] Faiss re-registration failed: {re_err}")

        # 1) appel MCP (chronométré)
        _call_start_monotonic = _time.perf_counter()
        _call_start_dt = datetime.now(timezone.utc)
        result = _MCP.tools_call(handle, tool_name, args)
        _call_end_dt = datetime.now(timezone.utc)
        _call_end_monotonic = _time.perf_counter()
        _duration = _call_end_monotonic - _call_start_monotonic
        #print("MCP result:", result)

        # Petite heuristique de source (optionnelle)
        source_hint = None
        if handle == "github":
            source_hint = "https://api.github.com"
        elif handle == "postgres":
            source_hint = os.environ.get("PG_DSN") or "urn:postgres"

        # 2) cas JSON-LD natif
        if isinstance(result, dict) and result.get("media_type") == "application/ld+json":
            jsonld_data = result.get("jsonld")
            # capture prompt if present in result
            prompt_text = result.get("prompt") if isinstance(result, dict) else None
            graph_uri = BNode()
            named_graph = store.get_context(graph_uri)
            if isinstance(jsonld_data, list):
                # Wrap list into @graph container
                payload_obj = {"@context": "https://schema.org/", "@graph": jsonld_data}
                payload = json.dumps(payload_obj)
            elif isinstance(jsonld_data, dict):
                payload = json.dumps(jsonld_data)
            else:
                payload = str(jsonld_data)
            try:
                named_graph.parse(data=payload, format="json-ld")
            except Exception as e:
                logger.warning(f"[MCP] Error parsing JSON-LD: {e}")
            # Status (succès implicite si pas de champ status)
            status_val = result.get("status", "success") if isinstance(result, dict) else "success"
            named_graph.add((graph_uri, URIRef("http://example.org/status"), Literal(status_val)))
            _attach_prov(named_graph, graph_uri, handle, tool_name, args, source_hint,
                         start_dt=_call_start_dt, end_dt=_call_end_dt, duration_s=_duration,
                         prompt_text=prompt_text)
            logger.debug("Named graph has %d triples", len(named_graph))
            return graph_uri

        # 3) mapper dédié si disponible
        mapper = PROFILE_MAPPERS.get(tool_name)
        if mapper and isinstance(result, (dict, list)):
            jsonld = mapper(result)
            giri = _jsonld_to_named_graph(jsonld, graph_name_hint)
            gctx = store.get_context(giri)
            status_val = result.get("status", "success") if isinstance(result, dict) else "success"
            gctx.add((giri, URIRef("http://example.org/status"), Literal(status_val)))
            prompt_text = result.get("prompt") if isinstance(result, dict) else None
            _attach_prov(store.get_context(giri), giri, handle, tool_name, args, source_hint,
                         start_dt=_call_start_dt, end_dt=_call_end_dt, duration_s=_duration,
                         prompt_text=prompt_text)
            return giri

        # 4) heuristique générique JSON -> JSON-LD
        if isinstance(result, (dict, list)):
            print("MCP JSON:", json.dumps(result))
            jsonld_data = json_to_jsonld(result)
            graph_uri = BNode()
            named_graph = store.get_context(graph_uri)
            named_graph.parse(data=json.dumps(jsonld_data), format="json-ld")
            status_val = result.get("status", "success") if isinstance(result, dict) else "success"
            named_graph.add((graph_uri, URIRef("http://example.org/status"), Literal(status_val)))
            prompt_text = result.get("prompt") if isinstance(result, dict) else None
            _attach_prov(named_graph, graph_uri, handle, tool_name, args, source_hint,
                         start_dt=_call_start_dt, end_dt=_call_end_dt, duration_s=_duration,
                         prompt_text=prompt_text)
            return graph_uri

        # 5) fallback: pas de RDF possible
        logger.warning(f"[MCP] Non-RDF output for tool {tool_name}: {type(result)}")
        return None

    except Exception as e:
        logger.error(f"[MCP] Error calling tool: {e}")
        traceback.print_exc()
        try:
            # Tentative d'ajout d'un graphe minimal de provenance avec status=error + durée si dispo
            graph_uri = BNode()
            named_graph = store.get_context(graph_uri)
            named_graph.add((graph_uri, URIRef("http://example.org/status"), Literal("error")))
            named_graph.add((graph_uri, URIRef("http://example.org/error_message"), Literal(str(e)[:500])))
            # Si les variables de timing existent
            if '_call_start_dt' in locals():
                end_dt = datetime.now(timezone.utc)
                if '_call_start_monotonic' in locals() and '_call_end_monotonic' not in locals():
                    end_mono = _time.perf_counter()
                    duration_s = end_mono - _call_start_monotonic
                else:
                    duration_s = None
                _attach_prov(named_graph, graph_uri, handle, tool_name, args if 'args' in locals() else {},
                             source_hint=None,
                             start_dt=_call_start_dt,
                             end_dt=end_dt,
                             duration_s=duration_s)
            return graph_uri
        except Exception as prov_e:
            logger.debug(f"[MCP] Unable to record error provenance: {prov_e}")
            return None
