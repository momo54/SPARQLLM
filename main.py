import importlib

# Import RDFLib components
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, FOAF

from rdflib.plugins.sparql.sparql import (
    QueryContext,
)
from rdflib.plugins.sparql.parserutils import CompValue
from  serviceLLM import evalServiceLLMQuery
from  serviceSE import evalServiceSEQuery
from funcSE import Google
from funcLLM import LLM

# monkey patching the evalServiceQuery function to use the serviceLLM module
import rdflib.plugins.sparql.evaluate
#from rdflib.plugins.sparql.evaluate import evalServiceQuery
evalServiceQuery_orig = rdflib.plugins.sparql.evaluate.evalServiceQuery


def my_evalServiceQuery(ctx: QueryContext, part: CompValue):
    res = {}
    if str(part.get('term')) == "http://chat.openai.com":
        return evalServiceLLMQuery(ctx, part)
    if str(part.get('term')) == "http://www.google.com":
        return evalServiceSEQuery(ctx, part)
    else:
        return evalServiceQuery_orig(ctx, part)

rdflib.plugins.sparql.evaluate.evalServiceQuery = my_evalServiceQuery
importlib.reload(rdflib)



def create_simple_graph():
    # Create a new graph
    g = Graph()
    # Define namespaces
    ex = Namespace("http://example.org/")
    # Add triples to the graph
    # Adding details for Bob
    g.add((URIRef("http://example.org/person/bob"), RDF.type, FOAF.Person))
    g.add((URIRef("http://example.org/person/bob"), FOAF.name, Literal("Bob")))
    g.add((URIRef("http://example.org/person/bob"), FOAF.age, Literal(30)))
    # Adding details for Alice and linking her to Bob
    g.add((ex.alice, RDF.type, FOAF.Person))
    g.add((ex.alice, FOAF.name, Literal("Alice")))
    g.add((ex.alice, FOAF.knows, URIRef("http://example.org/person/bob")))  # Alice knows Bob
    return g

def simple_query():
    g=create_simple_graph()
    query="""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>
        SELECT ?person ?name ?answer WHERE {
            ?person rdf:type foaf:Person .
            ?person foaf:name ?name .
            SERVICE <http://chat.openai.com> { BIND ("give me an URL for the person ?name" as ?answer) } 
        }"""
    # Querying the graph using SPARQL
    qres = g.query(query)

    # Print query results
    print("SPARQL Query Results:")
    for row in qres:
        print(f"Person: {row.person}, Name: {row.name}, Answer: {row.answer}")

def cominlabs_query():
    g = Graph()
    g.parse("cominlabs2023.rdf", format="xml")
    query="""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX vcard: <http://www.w3.org/2001/vcard-rdf/3.0#>
PREFIX bibtex: <http://www.edutella.org/bibtex#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?pub  ?journal ?llm WHERE {
            ?pub dct:isPartOf ?part .
            ?part dc:title ?journal .
            SERVICE <http://chat.openai.com> { 
                BIND ("In the scientific world, give me the impact factor or CORE ranking as JSON for the journal or conference entitled ?journal" as ?llm) 
            } 
        } """
    qres = g.query(query)
    for row in qres:
        print(f"{row.pub}  {row.journal} {row.llm}")

def dbpedia_query():
    g = Graph()
    query="""
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX dbp: <http://dbpedia.org/property/>

SELECT ?film ?url WHERE {
  SERVICE <http://dbpedia.org/sparql> {
    SELECT ?film ?abstract {
      ?film dbo:wikiPageWikiLink dbr:Category:English-language_films .
      ?film dbo:abstract ?abstract .
      FILTER (LANG(?abstract) = "en")
    } LIMIT 1 
  } .
  SERVICE <http://www.google.com> {
    BIND ("Who sells ?film" as ?url) 
  }
} LIMIT 10
"""
    qres = g.query(query)
    for row in qres:
        print(f"{row.film}  {row.url}")


if __name__ == "__main__":
#   simple_query()
    cominlabs_query()
#    dbpedia_query()
