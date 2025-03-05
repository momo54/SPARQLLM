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

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")

headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

# link_to should be UrI.
def SEGRAPH(keywords,link_to, nb_results=5):
    global store

    config = ConfigSingleton()
    se_url = config.config['Requests']['SLM-CUSTOM-SEARCH-URL'].format(se_cx_key=se_cx_key,se_api_key=se_api_key)
    #max_links = int(config.config['Requests']['SLM-SEARCH-MAX-LINKS'])
    max_links = int(nb_results)

    logger.debug(f"SEGRAPH: ({keywords},{link_to},{type(link_to)},se_url:{se_url}, max_links:{max_links})")

    if not isinstance(link_to,URIRef) :
        raise ValueError("SEGRAPH 2nd Argument should be an URI")

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
        logger.debug(f"SEGRAPH got nb links:{len(links)}")        

#        for item in json_data.get('items', []) :
        for item in links[:max_links]:
            #print(f"Adding {item['link']} to {link_to}")
            logger.debug(f"SEGRAPH found: {item}")
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))        
            #for s, p, o in named_graph:
            #    print(f"Subject: {s}, Predicate: {p}, Object: {o}")
        return graph_uri



# run with : python -m SPARQLLM.udf.segraph
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SEGRAPH"), SEGRAPH)

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))  

    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s) AS ?graph)
#            { select * {
                GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
 #               } limit 2
#          }
        }
        """

    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)


