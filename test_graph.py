from rdflib import Graph, ConjunctiveGraph,  URIRef, Literal, Namespace
from SPARQLLM import store

## super important !!
## need one store per request as graph are created dynamically during query execution.
#store = ConjunctiveGraph()

store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("http://example.org/graph1")))  

store.get_context("http://example.org/graph1").add((URIRef("http://example.org/subject1"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph2")))
store.get_context("http://example.org/graph2").add((URIRef("http://example.org/graph2"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph3")))

query_str = """
        PREFIX ex: <http://example.org/>
        SELECT *
        WHERE {
            ?s <http://example.org/hasValue> ?value .
            BIND(?value AS ?graph1)
                GRAPH ?graph1 {?s <http://example.org/has_uri> ?uri}    
            BIND(?uri AS ?graph2)
                GRAPH ?graph2 {?uri <http://example.org/has_uri> ?test}    

        }
        """

for g in store.contexts():  # context() retourne tous les named graphs
    print(f"main store named graphs: {g.identifier}")


result = store.query(query_str)

for row in result:
    for var in result.vars:  # results.vars contient les noms des variables
        print(f"{var}: {row[var]}")  # Afficher nom de colonne et valeur
    print()  # Séparation entre les lignes
