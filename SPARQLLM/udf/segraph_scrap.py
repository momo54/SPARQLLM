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

from search_engines import Google

engine = Google()

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")


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
def SEGRAPH_scrap(keywords,link_to):
    global store
    logging.debug(f"SEGRAPH_scap: id Store {id(store)}")

    #print(f"Google store: {id(store)}")
    logging.debug(f"SEGRAPH_scrap: ({keywords},{link_to},{type(link_to)})")

    if not isinstance(link_to,URIRef) :
        raise ValueError("SEGRAPH_scrap 2nd Argument should be an URI")

    se_url=f"https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}"

    graph_uri = URIRef("http://google.com/"+hashlib.sha256(keywords.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logging.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:

        named_graph = store.get_context(graph_uri)

        # Send the request to Google search
#        se_url = f"{se_url}&q={quote(keywords)}"

        logging.debug(f"se_url={se_url}")

#        headers = {'Accept': 'application/json'}
#        request = Request(se_url, headers=headers)
#        response = urlopen(request)

        results = engine.search(keywords,pages=1)
        links = results.links()


        for item in links:
            #print(f"Adding {item['link']} to {link_to}")
            logging.debug(f"SEGRAPH found: {item}")
            named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))        
            #for s, p, o in named_graph:
            #    print(f"Subject: {s}, Predicate: {p}, Object: {o}")
        return graph_uri


# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/SEGRAPH-SC"), SEGRAPH_scrap)

# run with python -m SPARQLLM.udf.segraph_scrap
if __name__ == "__main__":


    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("university nantes", datatype=XSD.string)))  

    # # SPARQL query using the custom function
    # query_str = """
    #     PREFIX ex: <http://example.org/>
    #     SELECT ?s ?uri
    #     WHERE {
    #         ?s ?p ?value .
    #         BIND(ex:SEGRAPH(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s) AS ?graph)
    #         GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
    #     }
    #     """

    # # Execute the query
    # query = prepareQuery(query_str)
    # result = store.query(query)

    # # Display the results
    # for row in result:
    #     print(f"Result : {row}")

    query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?uri
        WHERE {
            ?s ?p ?value .
            BIND(ex:SEGRAPH-SC(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value)),?s) AS ?graph)
#            { select * {
                GRAPH ?graph {?s <http://example.org/has_uri> ?uri}    
 #               } limit 2
#          }
        }
        """

    # Execute the query
    query = prepareQuery(query_str)
    result = store.query(query)

    # Display the results
    for row in result:
        print(f"Result : {row}")


