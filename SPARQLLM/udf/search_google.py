from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json
import hashlib

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import logging
logger = logging.getLogger(__name__)



headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

config = ConfigSingleton()
# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("GOOGLE_API_KEY")
se_cx_key=os.environ.get("GOOGLE_CX")


# link_to should be UrI.
def search_google(keywords,link_to, nb_results=5):
    """
        Searches Google Custom Search for the given keywords, retrieves the top results, and returns the graph URI containing the results.

        Args:
            keywords (str): The search keywords to find in Google Custom Search.
            link_to (URIRef): The URI to link the search results to in the graph.
            nb_results (int, optional): The number of top results to retrieve. Defaults to 5.

        Returns:
            URIRef: The URI of the named graph containing the search results. If an error occurs, raises a ValueError.
    """
    global store
    

    
    if se_api_key is None:
        raise ValueError("GOOGLE_API_KEY is not set. Using default value, which may not work for real API calls.")

    if se_cx_key is None:
        raise ValueError("GOOGLE_CX is not set. Using default value, which may not work for real API calls.")
   
    if config.config['Requests']['SLM-CUSTOM-SEARCH-URL'] is None:
        raise ValueError("SLM-CUSTOM-SEARCH-URL is not set. Using default value, which may not work for real API calls.")
    
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key,se_api_key=se_api_key)

    max_links = int(nb_results)
    logger.debug(f"({keywords},{link_to},{type(link_to)},se_url:{se_url}, max_links:{max_links})")


    graph_uri = URIRef("http://google.com/"+hashlib.sha256(keywords.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:
        named_graph = store.get_context(graph_uri)

        # Send the request to Google search
        se_url = f"{se_url}&q={quote(keywords)}"

        logger.debug(f"se_url={se_url}")

        headers = {'Accept': 'application/json'}
        request = Request(se_url, headers=headers)
        response = urlopen(request)
        json_data = json.loads(response.read().decode('utf-8'))

        links = [item['link'] for item in json_data.get('items', [])]
        logger.debug(f"nb links:{len(links)}")        

        for item in links[:max_links]:
            logger.debug(f"found {item}")
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))        
        return graph_uri



