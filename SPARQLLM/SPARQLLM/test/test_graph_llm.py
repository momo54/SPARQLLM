##
## Just for debugging purpose
## Test LLM triggered from a binding coming from a graph.
## Should be the same when binding will come from Search Engine.
##


import rdflib
from rdflib import Graph, ConjunctiveGraph,  URIRef, Literal, Namespace
from rdflib.plugins.sparql.evaluate import evalGraph, evalServiceQuery, evalLazyJoin

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.udf.llmgraph import LLMGRAPH
from SPARQLLM.utils.explain import explain


store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("http://example.org/graph1")))  

store.get_context("http://example.org/graph1").add((URIRef("http://example.org/subject1"), URIRef("http://example.org/has_uri"), URIRef("https://zenodo.org/records/13955291")))
store.get_context("http://example.org/graph2").add((URIRef("http://example.org/graph2"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph3")))

#store.get_context("https://zenodo.org/records/13955291").add((URIRef("https://zenodo.org/records/13955291"), URIRef("http://example.org/has_schema_type"), URIRef("http://example.org/graph5")))

query_str = """
        PREFIX ex: <http://example.org/>
        SELECT ?s ?value ?uri ?p ?o
        WHERE {
            ?s <http://example.org/hasValue> ?value .
            BIND(?value AS ?graph1)
                GRAPH ?graph1 {?s <http://example.org/has_uri> ?uri} .
            BIND(ex:GETTEXT(?uri,400) AS ?page) . 
            BIND(ex:LLMGRAPH(REPLACE("Extrait en JSON-LD la représentation schema.org de : PAGE ","PAGE",STR(?page)),?value) AS ?graph2) .
               GRAPH ?graph2 {?value ?p ?o}    
        }
        """


explain(query_str)

result = store.query(query_str)

for row in result:
    for var in result.vars:  
        print(f" results {var}: {row[var]}") 
    print()  # Séparation entre les lignes
