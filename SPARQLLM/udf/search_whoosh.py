from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

from whoosh.index import open_dir
from whoosh.qparser import QueryParser
from whoosh.qparser import MultifieldParser,WildcardPlugin
import hashlib

import logging
logger = logging.getLogger(__name__)

index_dir = "./data/index"
ix = open_dir(index_dir)

# Carefull to return the good types !!
def searchWhoosh(keywords,link_to,nb_results=5):
    global store

    config = ConfigSingleton()
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])
    max_links = int(config.config['Requests']['SLM-SEARCH-MAX-LINKS'])


    nb_results = int(nb_results)
    logger.debug(f"searchWhoosh: (keyword: {keywords},link to: {link_to}, , nb_results: {nb_results})")

    if not isinstance(link_to,URIRef) :
        raise ValueError("link_to should be an URI")
    
    graph_uri = URIRef("http://whoosh.org/"+hashlib.sha256(keywords.encode()).hexdigest())

    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri

    named_graph = store.get_context(graph_uri)

    with ix.searcher() as searcher:
        parser=MultifieldParser(["content"], ix.schema)
        parser.add_plugin(WildcardPlugin())
        query = parser.parse(keywords+"*")
        results = searcher.search(query, limit=10)  # Limit to top 10 results
        
        if results:
            for i, result in enumerate(results):
                if i >= nb_results:
                    break
                item=URIRef("file:/"+result['filename'])
                logger.debug(f"Whoosh {item} {result.score}")
                named_graph.add((link_to, URIRef("http://example.org/has_uri"), item)) 
#                named_graph.add((item, URIRef("http://example.org/has_score"), Literal(result.score, datatype=XSD.float))))          
    return graph_uri 


#  python -m SPARQLLM.udf.search_whoosh
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SE"), searchWhoosh)
    
    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("paris", datatype=XSD.string)))  

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?city ?uri
    WHERE {
        ?s ?p ?city .
        BIND(ex:SE(CONCAT("cinema ",STR(?city)),?s,5) AS ?graph)
        GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
    }
    """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)

