from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from string import Template
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

import os
import json
import hashlib

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import logging
logger = logging.getLogger(__name__)

# Headers for the HTTP request to emulate a browser
headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # Optional header to emulate a browser
}

# Load configuration settings
config = ConfigSingleton()
# Retrieve the Google API key from environment variables
se_api_key = os.environ.get("GOOGLE_API_KEY")
# Retrieve the Google Custom Search Engine ID from environment variables
se_cx_key = os.environ.get("GOOGLE_CX")

def search_google(keywords, link_to, nb_results=5):
    """
    Searches Google using the provided keywords and updates a named graph with the results.

    Args:
        keywords (str): The search keywords.
        link_to (str): The URI of an entity to link to.
        nb_results (int): The number of search results to retrieve.

    Returns:
        URIRef: The URI of the new named graph.

    Raises:
        ValueError: If the API key or Custom Search Engine ID is not set.
    """
    global store

    # Check if the Google API key is set
    if se_api_key is None:
        raise ValueError("GOOGLE_API_KEY is not set. Using default value, which may not work for real API calls.")

    # Check if the Google Custom Search Engine ID is set
    if se_cx_key is None:
        raise ValueError("GOOGLE_CX is not set. Using default value, which may not work for real API calls.")

    # Check if the custom search URL is set in the configuration
    if config.config['Requests']['SLM-CUSTOM-SEARCH-URL'] is None:
        raise ValueError("SLM-CUSTOM-SEARCH-URL is not set. Using default value, which may not work for real API calls.")

    # Format the custom search URL with the API key and Custom Search Engine ID
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key, se_api_key=se_api_key)

    max_links = int(nb_results)
    logger.debug(f"({keywords},{link_to},{type(link_to)},se_url:{se_url}, max_links:{max_links})")

    # Create a unique