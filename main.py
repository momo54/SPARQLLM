import importlib

# Import RDFLib components
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, FOAF

# monkey patching the evalServiceQuery function to use the serviceLLM module
import serviceLLM
import rdflib.plugins.sparql.evaluate
#from rdflib.plugins.sparql.evaluate import evalServiceQuery
evalServiceQuery_orig = rdflib.plugins.sparql.evaluate.evalServiceQuery
rdflib.plugins.sparql.evaluate.evalServiceQuery = serviceLLM.my_evalServiceQuery
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
#        PREFIX dct: <http://purl.org/dc/terms/>
#        PREFIX dc: <http://purl.org/dc/elements/1.1/>
#        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
#        PREFIX vcard: <http://www.w3.org/2001/vcard-rdf/3.0#>
        PREFIX bibtex: <http://www.edutella.org/bibtex#>
#        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#">
        SELECT ?s0  ?o ?answer WHERE {
            ?s0 dct:isPartOf ?part .
            ?part dc:title ?o .
            SERVICE <http://chat.openai.com> { 
                BIND ("In the scientific world, give me the metrics as JSON for the journal or conference entitled ?o" as ?answer) 
            } 
  
        } limit 1"""
    qres = g.query(query)
    for row in qres:
        print(f"{row.s0}  {row.o} {row.answer}")

if __name__ == "__main__":
#   simple_query()
    cominlabs_query()
