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

import logging
import time 
from search_engines import Google, Duckduckgo, Bing 

engine = Google()
#engine=Duckduckgo() # seems to get 202 response (accepted but delayed)
#engine=Bing() # URLs looks not to be correcly formatted


headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

def named_graph_exists(conjunctive_graph, graph_uri):
    for g in conjunctive_graph.contexts():  # context() retourne tous les named graphs
        if g.identifier == graph_uri:
            return True
    return False

# link_to should be UrI.
def SEGRAPH_scrap(keywords,link_to,nb_results=5):
    global store
    #    logging.debug(f"SEGRAPH_scrap: id Store {id(store)}")

    
    nb_results = int(nb_results)
    logging.debug(f"SEGRAPH_scrap: (keyword: {keywords},link to: {link_to}, , nb_results: {nb_results})")

    if not isinstance(link_to,URIRef) :
        raise ValueError("SEGRAPH_scrap 2nd Argument should be an URI")


    graph_uri = URIRef("http://google.com/"+hashlib.sha256(keywords.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logging.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri

    logging.debug("Waiting for 5 seconds...")
    time.sleep(5)

    named_graph = store.get_context(graph_uri)
    try:
        # ok i recreate a new engine each time, but it seems to be the only way to get it working 
        engine = Google()
        #engine=Duckduckgo() # seems to get 202 response (accepted but delayed)
        #engine=Bing() # URLs looks not to be correcly formatted

        results = engine.search(keywords,pages=1)
        links = results.links()

        logging.debug(f"SEGRAPH_scrap  : got {len(links)} links on first page, {links},{type(links)}, nb_results: {nb_results}, {type(nb_results)}")
        for item in links[:nb_results]:
            logging.debug(f"SEGRAPH found: {item}")
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))        
            #for s, p, o in named_graph:
            #    print(f"Subject: {s}, Predicate: {p}, Object: {o}")
    except Exception as e:
        logging.debug(f"SEGRAPH_scrap: Error during search: {e}")
        return graph_uri
    return graph_uri


# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/SEGRAPH-SC"), SEGRAPH_scrap)

# run with python -m SPARQLLM.udf.segraph_scrap
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

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

    # Display the results
    for row in result:
        print(f"Result : {row}")


