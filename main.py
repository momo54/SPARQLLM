import importlib

# Import RDFLib components
from rdflib.namespace import RDF, FOAF
from rdflib import Graph, URIRef, Literal, Namespace

# Import custom functions and services
import custom

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


def func_query():
    g = Graph()
    query="""
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX ex: <http://example.org/>

SELECT DISTINCT ?universityLabel ?uri ?nbetu ?result
WHERE {
    SERVICE <http://dbpedia.org/sparql> {
      SELECT *  where {
        ?university a dbo:University ;
               dbo:country dbr:France ;
               dbo:numberOfStudents ?nbetu .
       OPTIONAL { ?university rdfs:label ?universityLabel . 
       FILTER (lang(?universityLabel) = "fr") }
      } LIMIT 5
    }
    BIND(ex:Google(REPLACE("Je veux savoir le nombre d'étudiants à UNIV ","UNIV",STR(?universityLabel))) AS ?uri)
    BIND(ex:BS4(?uri) AS ?page)   
    BIND(ex:LLM(REPLACE("trouve le nombre d'étudiant dans le texte suivant et renvoie un entier avec son contexte :<text>PAGE</text>","PAGE",str(?page))) AS ?result)
}
"""

    qres = g.query(query)
    for row in qres:
        print(f"row : {row['universityLabel']} {row['uri']} {row['nbetu']} {row['result']}")


if __name__ == "__main__":
#   simple_query()
#    cominlabs_query()
#    dbpedia_query()
    func_query()
