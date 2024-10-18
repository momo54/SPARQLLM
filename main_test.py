import importlib

# Import RDFLib components
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, FOAF

#from  serviceLLM import evalServiceLLMQuery
#from  serviceSE import evalServiceSEQuery
import funcSE 
import funcLLM 


def dbpedia_query():
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
    dbpedia_query()