import rdflib
from rdflib import Graph, Dataset,  URIRef
from utils.explain import explain

from rdflib.plugins.sparql.algebra import  _traverseAgg
from rdflib.plugins.sparql.algebra import translateQuery, translateUpdate, analyse
from rdflib.plugins.sparql.parser import parseQuery, parseUpdate
from rdflib.plugins.sparql.algebra import pprintAlgebra
from rdflib.plugins.sparql.parserutils import prettify_parsetree


store=Dataset()
store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("http://example.org/graph1")))  
store.get_context("http://example.org/graph1").add((URIRef("http://example.org/subject1"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph2")))
store.get_context("http://example.org/graph2").add((URIRef("http://example.org/subject1"), URIRef("http://example.org/has_uri"), URIRef("http://example.org/graph3")))


query_str = """
        SELECT *
        WHERE {
           ?s <http://example.org/hasValue> ?g1 .
            Bind(?g1 as ?graph1)
            graph ?graph1 {?s <http://example.org/has_uri> ?g2} .
            Bind(?g2 as ?graph2)
            graph ?graph2 {?s <http://example.org/has_uri> ?g3}  
            bind(?g3 as ?graph3)

        }
        """
explain(query_str)

pq = parseQuery(query_str)
tq = translateQuery(pq)

_traverseAgg(tq, visitor=analyse)
print(pprintAlgebra(tq))

result = store.query(query_str)
for row in result:
    for var in result.vars:  
        print(f" results {var}: {row[var]}") 
    print()  


