
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from SPARQLLM import store

graph_uri = "http://example.org/graph1"
uri="http://example.org/subject1"

##store = ConjunctiveGraph()
named_graph = store.get_context(graph_uri)

named_graph.add((URIRef(uri+"/test"), URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), Literal(5, datatype=XSD.integer)))

insert_query_str = f"""
            INSERT {{
                <{uri}> <http://example.org/has_schema_type> ?subject }}
            WHERE {{
                ?subject a ?type 
            }}"""
print(f"Query: {insert_query_str}")
named_graph.update(insert_query_str)

qres = named_graph.query("""SELECT ?s WHERE { ?s ?p ?o }""")

print("After update:")
for row in qres:
    print(f"{row}")