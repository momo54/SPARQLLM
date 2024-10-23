
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import funcSE

from SPARQLLM import store


def LLMGRAPH_fake(prompt,uri):
    global store
#    print(f"LLMGRAPH_fake: id Store {id(store)}")
    print(f"LLMGRAPH_fake  uri: {uri}, Prompt: {prompt[:100]} <...>")
#    for g in store.contexts():  # context() retourne tous les named graphs
#        print(f"LLMGRAPH_fake store named graphs: {g.identifier}")

    if not isinstance(uri,URIRef) :
        print(f"LLMGRAPH_fake 2nd Argument should be an URI")
        raise ValueError("LLMGRAPH_fake 2nd Argument should be an URI")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    try:
    # Extract the generated text from the response
        jsonld_data = """
        {
            "@context": "http://schema.org/",
            "@type": "Person",
            "name": "Jane Doe",
            "jobTitle": "Professor",
            "telephone": "(425) 123-4567",
            "url": "http://www.janedoe.com"
            }
        """
        #named_graph.parse(data=jsonld_data, format="json-ld")
        named_graph.add((uri, URIRef("http://example.org/has_schema_type"), Literal(5, datatype=XSD.integer)))

        # #link new triple to bag of mappings
        # insert_query_str = f"""
        #     INSERT  {{
        #         <{uri}> <http://example.org/has_schema_type> ?subject .}}
        #     WHERE {{
        #         ?subject a ?type .
        #     }}"""
        # #print(f"Query: {insert_query_str}")
        # named_graph.update(insert_query_str)

        for subj, pred, obj in named_graph:
            print(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")


#        res=named_graph.query("""SELECT ?s ?o WHERE { ?s <http://example.org/has_schema_type> ?o }""")
#        for row in res:
#            print(f"LLMGRAPH_fake existing types in JSON-LD: {row}")
#        for g in store.contexts():  # context() retourne tous les named graphs
#            print(f"LLMGRAPH_fake store graphs: {g.identifier}, len {g.__len__()}")



    except Exception as e:
        print(f"LLMGRAPH_fake Parse Error: {e}")

    return graph_uri 
#    return URIRef("http://dbpedia.org/sparql")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/LLMGRAPH_fake"), LLMGRAPH_fake)



if __name__ == "__main__":

    # store is a global variable for SPARQLLM
    # not good, but see that later...
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?uri ?o1  WHERE {
        {
            SELECT ?s ?uri WHERE {
                ?s ?p ?uri .
            }
        }
        BIND(ex:BS4(?uri) AS ?page)  
        BIND(ex:LLMGRAPH_fake(REPLACE("Extrait en JSON-LD la représentation schema.org de : PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . ?o ?p1 ?o1}    
    }
    """

    # Execute the query
    query = prepareQuery(query_str)
    result = store.query(query)

    for row in result:
        for var in result.vars:  # results.vars contient les noms des variables
            print(f"{var}: {row[var]}")  # Afficher nom de colonne et valeur
    print()  # Séparation entre les lignes
