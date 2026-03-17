import hashlib
import rdflib
from rdflib import Graph, Literal, URIRef, BNode
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

import requests
import html
import html2text
import unidecode
from urllib.parse import urlparse


from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table

import logging
logger = logging.getLogger(__name__)

config = ConfigSingleton()

# Cache: absolute file path -> deterministic graph URIRef (avoids re-parsing same file)
_LOAD_CACHE: dict = {}

def read_rdf(path_uri,format="turtle"):
    logger.debug(f"uri: {path_uri}")    
    graph_uri = BNode()    
    named_graph = store.get_context(graph_uri)

    try:
        path= urlparse(path_uri).path
        logger.debug(f"Reading {path} with format {format}")
        named_graph.parse(path, format=str(format))
        logger.debug(f"Graph {graph_uri} has {len(named_graph)} triples")

    except requests.exceptions.RequestException as e:
        logger.error("Error reading {uri} : {e}")
        return graph_uri
    return graph_uri


def load_rdf_file(file_path: str, format: str | None = None):
    """Load an RDF file from a local filesystem path into the global store and
    return the named graph URI. Similar to read_rdf() but strictly for local files
    (no URL parsing) and with light format auto-detection.

    The graph URI is deterministic (based on the absolute path hash) and the file
    is only parsed once per process — subsequent calls with the same path hit the cache.

    Parameters
    ----------
    file_path : str
        Path to a local RDF file (e.g. data/events.ttl)
    format : str | None
        Explicit rdflib parse format (e.g. "turtle", "nt", "xml", "json-ld"). If None,
        the function will guess from the file extension (.ttl, .nt, .nq, .rdf, .xml, .jsonld, .trig, .n3).

    Returns
    -------
    rdflib.term.URIRef
        The graph URI in the shared store.
    """
    abs_path = os.path.abspath(file_path)

    # Fast path: already loaded
    if abs_path in _LOAD_CACHE:
        logger.debug(f"LOAD: cache hit for {abs_path}")
        return _LOAD_CACHE[abs_path]

    # Deterministic URI derived from the absolute path so subqueries can reuse it
    h = hashlib.sha256(abs_path.encode()).hexdigest()[:24]
    graph_uri = URIRef(f"urn:loadrdf:{h}")

    if not os.path.exists(abs_path):
        logger.warning(f"LOAD: file does not exist: {abs_path}")
        _LOAD_CACHE[abs_path] = graph_uri
        return graph_uri

    # Guess format if not provided
    if format is None:
        ext = os.path.splitext(abs_path)[1].lower()
        format_map = {
            ".ttl": "turtle",
            ".nt": "nt",
            ".nq": "nquads",
            ".trig": "trig",
            ".jsonld": "json-ld",
            ".rdf": "xml",
            ".xml": "xml",
            ".n3": "n3",
        }
        format = format_map.get(ext, "turtle")

    named_graph = store.get_context(graph_uri)
    try:
        logger.debug(f"LOAD: parsing {abs_path} as {format}")
        named_graph.parse(abs_path, format=str(format))
        logger.info(f"LOAD: graph {graph_uri} loaded with {len(named_graph)} triples from {abs_path}")
    except Exception as e:
        logger.error(f"LOAD: error parsing {abs_path}: {e}")

    _LOAD_CACHE[abs_path] = graph_uri
    return graph_uri

