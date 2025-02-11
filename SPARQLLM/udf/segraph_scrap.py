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

from googlesearch import search


from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import time
from search_engines import Google, Duckduckgo, Bing


import logging
logger = logging.getLogger(__name__)


engine = Google()
#engine=Duckduckgo() # seems to get 202 response (accepted but delayed)
#engine=Bing() # URLs looks not to be correcly formatted

headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}


# link_to should be UrI.
def SEGRAPH_scrap(keywords, link_to, nb_results=5):

    config = ConfigSingleton()
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])

    nb_results = int(nb_results)
    logger.debug(f"SEGRAPH_scrap: (keyword: {keywords}, link to: {link_to}, nb_results: {nb_results})")

    if not isinstance(link_to, URIRef):
        raise ValueError("SEGRAPH_scrap 2nd Argument should be an URI")

    graph_uri = URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())
    if named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri

    logger.debug(f"Waiting for {wait_time} seconds...")
    time.sleep(wait_time)

    named_graph = store.get_context(graph_uri)
    try:
        results = search(keywords)
        logger.debug(f"Search results: {results}")
        for result in results:
            logger.debug(f"SEGRAPH found: {result}")
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(result)))
    except Exception as e:
        logger.debug(f"SEGRAPH_scrap: Error during search: {e}")
        return graph_uri
    return graph_uri



# run with python -m SPARQLLM.udf.segraph_scrap
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SEGRAPH-SC"), SEGRAPH_scrap)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))  

    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH-SC(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s,5) AS ?graph)
                GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
        }
        """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)

