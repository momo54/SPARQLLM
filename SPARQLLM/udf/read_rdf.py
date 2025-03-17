import hashlib
import rdflib
from rdflib import Graph, Literal, URIRef
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

def read_rdf(path_uri,format="turtle"):
    """
        Reads an RDF file from the given URI, parses it into a named graph, and returns the graph URI.

        Args:
            path_uri (str): The URI of the RDF file to read.
            format (str, optional): The format of the RDF file (e.g., "turtle", "xml"). Defaults to "turtle".

        Returns:
            URIRef: The URI of the named graph containing the parsed RDF data. If an error occurs, returns the graph URI with no data.
    """
    logger.debug(f"uri: {path_uri}")    
    graph_uri = URIRef(f"http://readrdf.org/"+hashlib.sha256(path_uri.encode()).hexdigest())

    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    
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

