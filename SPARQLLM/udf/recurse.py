from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists
from SPARQLLM.udf.readdir import gettype, RDIR

import os
import json


import logging
import traceback

from pathlib import Path

rec_logger = logging.getLogger("recurse")


def recurse(query_str,gin,ginit,max_depth=10):
    rec_logger.debug(f"RECURSE enter : {query_str}, gin: {gin},{type(gin)}, ginit: {ginit},{type(ginit)}")
    all_graph_uri=URIRef("http://example.org/allg")    

    ## Output
    if  named_graph_exists(store, all_graph_uri):
        rec_logger.debug(f"Recurse Graph {all_graph_uri} already exists (good)")
        return None
    else:
        named_graph = store.get_context(all_graph_uri)

    def func_recurse_on(gin_rec,depth=0):
        print(f"RECURSE Recurse on : {gin_rec}")
        result = store.query(query_str,initBindings={gin:gin_rec})
        for row in result:
            rec_logger.debug(f"REcurse row: {row}")
            if row['gout'] == None:
                rec_logger.debug(f"REcurse row: get None")
                continue
            else:
                gout=URIRef(row['gout'])
                print(f"RECURSE Recurse on : {gin_rec} -> {gout}")
                named_graph.add((gin_rec, URIRef("http://example.org/has_graph"), gout))
                named_graph.add((gout, URIRef("http://example.org/has_depth"), Literal(depth, datatype=XSD.integer)))
                if depth <= max_depth:
                    func_recurse_on(gout,depth+1)
                else:
                    rec_logger.debug(f"RECURSE max depth :  {max_depth} reached")

    try:
        func_recurse_on(ginit,0)
    except Exception as e:
        rec_logger.debug(f"RECURSE Exception {e}")
        traceback.print_exc()


    # result=store.query(query_str,initBindings={'gin':ginit})   
    # for row in result:
    #     rec_logger.debug(f"Recurse: {row}")
    #     named_graph.add((ginit, URIRef("http://example.org/has_graph"), row['gout']))

    rec_logger.debug(f"RECURSE end: graph {all_graph_uri} has {len(all_graph_uri)} triples")
    return all_graph_uri

def testrec():

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT (MAX(?s) AS ?max_s)  WHERE {
        ## init recursion
        BIND(URI("file:///Users/molli-p/SPARQLLM") AS ?root)
        BIND(ex:RDIR(?root,?root) AS ?ginit)
        BIND(\"\"\"
        PREFIX ex: <http://example.org/>
        SELECT DISTINCT ?gout WHERE {
            GRAPH ?gin {
                ?root ex:has_path ?p1 .
                ?p1 ex:has_type ?t1.
                ?p1 ex:has_size ?s1 .
                filter (str(?t1)="directory")
            } 
            BIND(ex:RDIR(?p1,?p1) as ?gout)
            OPTIONAL {
                GRAPH ?gout {
                    ?p1 ex:has_path ?p2 .
                    ?p2 ex:has_type ?t2.
                    ?p2 ex:has_size ?s2 .
                }
            }
        } \"\"\" AS ?query_str)
        BIND(ex:RECURSE(?query_str,'?gin',?ginit,3) AS ?allg)
        GRAPH ?allg {?init ex:has_graph ?g }
        GRAPH ?g {?p ex:has_size ?s .}
    }"""        

    result = store.query(query_str)
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}")


# run with python -m SPARQLLM.udf.recurse
if __name__ == "__main__":
    rec_logger = logging.getLogger("recurse")
#    logging.basicConfig(level=logging.DEBUG)
    rec_logger.setLevel(logging.DEBUG)

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/RECURSE"), recurse)
    register_custom_function(URIRef("http://example.org/RDIR"), RDIR)


    testrec()
