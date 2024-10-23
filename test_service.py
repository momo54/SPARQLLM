import rdflib
from rdflib import Graph, Dataset,  URIRef
from explain import explain


store=Graph()
store.add((URIRef("http://dbpedia.org/resource/Napoleon"), URIRef("http://example.org/hasValue"), URIRef("https://dbpedia.org/sparql")))  

query_str = """
        SELECT *
        WHERE {
           ?s <http://example.org/hasValue> ?value .
#            <http://dbpedia.org/resource/Napoleon> ?p ?o
                       SERVICE ?value {?s <http://dbpedia.org/ontology/spouse> ?o}       
        }
        """
explain(query_str)
result = store.query(query_str)
for row in result:
    for var in result.vars:  
        print(f" results {var}: {row[var]}") 
    print()  


