from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import named_graph_exists


import os
import json


import logging

from pathlib import Path

def gettype(path):
    entry = Path(path)
    if entry.is_file():
        return Literal('file')
    elif entry.is_dir():
        return Literal('directory')
    elif entry.is_symlink():
        return Literal('symlink')
    else:
        return Literal('unknown')

def RDIR(dir,link_to):
    """
        Recursively reads the contents of a directory, creates a named graph with the directory structure, and returns the graph URI.

        Args:
            dir (str): The URI of the directory to read.
            link_to (URIRef): The URI to link the directory contents to in the graph.

        Returns:
            URIRef: The URI of the named graph containing the directory structure. If an error occurs, returns an error message as an RDF Literal.
    """
    logging.debug(f"RDIR enter : {dir}, {type(dir)}, link_to {link_to}, link_to: {type(link_to)}")    

    graph_uri=URIRef(dir)
    if  named_graph_exists(store, graph_uri):
        logging.debug(f"Graph {graph_uri} already exists (good)")
        return None
    else:
        named_graph = store.get_context(graph_uri)

    try:
        ## quite brutal...
        local_dir=str(dir)[7:]
        logging.debug(f"RDIR : listing {dir}, {local_dir}")
   
        files = os.listdir(local_dir)
        for file in files:
#            logging.debug(f"RDIR : found {file}, in {local_dir}")
            path=URIRef("file://"+os.path.join(local_dir, file))
            size=os.path.getsize(os.path.join(local_dir, file))
#            logging.debug(f"RDIR: path {path}, type {type(path)}")
            named_graph.add((link_to, URIRef("http://example.org/has_path"), path))
            named_graph.add((path, URIRef("http://example.org/has_size"), Literal(size, datatype=XSD.integer)))
            named_graph.add((path, URIRef("http://example.org/has_type"), gettype(os.path.join(local_dir, file))))  
        logging.debug(f"RDIR: graph {graph_uri} has {len(named_graph)} triples")
#        for s, p, o in named_graph:
#            print(f"Subject: {s}, Predicate: {p}, Object: {o}")


    except Exception as e:
        # En cas d'erreur HTTP ou de connexion
        logging.debug(f"RDIR: error {e}, on {dir}")
        return  Literal(f"Error retreiving {dir}")
    
    #don't forget
    return graph_uri


def test1():
    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("file:///Users/molli-p/SPARQLLM")))  

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?root ?g ?p1 ?t1 ?s1 ?p2 ?t2 ?p3 ?t3
    WHERE {
        ?s ?p ?root .
        BIND(ex:RDIR(?root,?root) AS ?g)
        GRAPH ?g {
            ?root ex:has_path ?p1 .
            ?p1 ex:has_type ?t1.
            ?p1 ex:has_size ?s1 .
            filter (str(?t1)="directory")
        } 
        BIND(ex:RDIR(?p1,?p1) as ?g2)
        OPTIONAL {
            GRAPH ?g2 {
                ?p1 ex:has_path ?p2 .
                ?p2 ex:has_type ?t2.
                ?p2 ex:has_size ?s2 .
                filter (str(?t2)="directory")
           }
            BIND(ex:RDIR(?p2,?p2) as ?g3)
            OPTIONAL {
                GRAPH ?g3 {
                    ?p2 ex:has_path ?p3 .
                    ?p3 ex:has_type ?t3.
                    ?p3 ex:has_size ?s3 .
                    filter (str(?t3)="directory")
                }
           }
       }
    }
    """

    # Execute the query
    result = store.query(query_str)

    # Display the results
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}") 

def testrec():

    query_init_str="""
    PREFIX ex: <http://example.org/>
    SELECT ?ginit
    WHERE {
        BIND(URI("file:///Users/molli-p/SPARQLLM") AS ?root)
        BIND(ex:RDIR(?root,?root) AS ?ginit)
        GRAPH ?gin {
            ?root ex:has_path ?p1 .
            ?p1 ex:has_type ?t1.
            ?p1 ex:has_size ?s1 .
        } 
    }
    """

    # SPARQL query using the custom function
    query_rec_str = """
    PREFIX ex: <http://example.org/>
    SELECT distinct ?gout 
    WHERE {
        GRAPH <#gin#> {
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
    }
    """

    query_final_str = """
        PREFIX ex: <http://example.org/>
        SELECT (MAX(?s) AS ?max_s) 
        WHERE {
            graph ?g {?p ex:has_size ?s .}
        }
    """

    # Execute the query
    result = store.query(query_init_str)
    first_result = list(result)[0] if len(result) > 0 else None
    ginit=first_result['ginit']
    print(f"ginit : {ginit}")

    def recurse_on(gin):
        print(f"Recurse on : {gin}")
        query_rec=query_rec_str.replace("#gin#",str(gin))
        #print(f"query_rec: {query_rec}")
        result = store.query(query_rec)
        for row in result:
            recurse_on(row['gout'])

    recurse_on(ginit)


    graph_names = [str(ctx.identifier) for ctx in store.contexts()]
    print("Liste des graphes :", graph_names)

    # query_final_str = """
    #     PREFIX ex: <http://example.org/>
    #     select (count(*) as ?nb) where {
    #         graph ?g {
    #             ?s ?p ?o
    #         }
    #     }
    # """


    result = store.query(query_final_str)
    print(f"Final query : {query_final_str}")
    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}")


# run with python -m SPARQLLM.udf.readdir
if __name__ == "__main__":
    #logging.basicConfig(level=logging.DEBUG)

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/RDIR"), RDIR)

#    test1()
    testrec()
