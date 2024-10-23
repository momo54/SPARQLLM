import importlib

# Import RDFLib components
from rdflib.namespace import RDF, FOAF
from rdflib import Graph, ConjunctiveGraph,  URIRef, Literal, Namespace

#import custom
from  explain import explain

# Import custom functions and services
from SPARQLLM import store

import funcSE 
import funcLLM 
import llmgraph
import segraph




def local_llmf():
    ##
    ## Local RDF + LLM (Func)
    ##
    g = Graph()
    g.parse("cominlabs2023.rdf", format="xml")
    query="""
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX dc: <http://purl.org/dc/elements/1.1/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX vcard: <http://www.w3.org/2001/vcard-rdf/3.0#>
        PREFIX bibtex: <http://www.edutella.org/bibtex#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX ex: <http://example.org/>
        
        SELECT ?pub  ?journal 
            (ex:LLM(REPLACE("In the scientific world, give me the impact factor or CORE ranking as JSON for the journal or conference entitled %PLACE%","%PLACE%",STR(?journal))) as ?llm) 
            WHERE {
                    ?pub dct:isPartOf ?part .
                    ?part dc:title ?journal .
                } """
    qres = g.query(query)
    for row in qres:
        print(f"{row.pub}  {row.journal} {row.llm}")


def dbpedia_seg():
    ##
    ## DBPEdia query + Search Engine (Graph)
    ##
    query_str="""
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dbr: <http://dbpedia.org/resource/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX dbp: <http://dbpedia.org/property/>
        PREFIX ex: <http://example.org/>

        SELECT ?film ?uri ?graph WHERE {
        SERVICE <http://dbpedia.org/sparql> {
            SELECT ?film ?abstract ?title {
            ?film dbo:wikiPageWikiLink dbr:Category:English-language_films .
            ?film dbo:abstract ?abstract .
            ?film rdfs:label ?title .
            FILTER (LANG(?abstract) = "en")
            } LIMIT 1 
        } . 
        BIND(ex:SEGRAPH(REPLACE("Shop selling the film entitled 'FILM' ","FILM",STR(?title)),?film) AS ?graph).
        GRAPH ?graph {?film <http://example.org/has_uri> ?uri}    
       } LIMIT 10
        """
    qres = store.query(query_str)
    for row in qres:
        print(f"{row}")




def query_sef_llmf():
    ##
    ## DBPEDIA + search engine (func) + LLM Graph
    ##
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
            BIND(ex:Google(REPLACE("FRANCE UNIV ","UNIV",STR(?universityLabel))) AS ?uri)
            BIND(ex:BS4(?uri) AS ?page)   
            BIND(ex:LLM(REPLACE("trouve le nombre d'étudiant dans le texte suivant et renvoie un entier avec son contexte :<text>PAGE</text>","PAGE",str(?page))) AS ?result)
        }
        """

    qres = store.query(query)
    for row in qres:
        print(f"row : {row['universityLabel']} {row['uri']} {row['nbetu']} {row['result']}")

def dpedia_sef_llmg():
    ##
    ## DBPEDIA + Google (func) + LLM (Graph)
    ##
    query="""
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dbr: <http://dbpedia.org/resource/>
        PREFIX ex: <http://example.org/>

        SELECT ?universityLabel ?uri  ?o
        WHERE {
            SERVICE <http://dbpedia.org/sparql> {
                SELECT *  where {
                    ?university a dbo:University ;
                        dbo:country dbr:France ;
                        dbo:numberOfStudents ?nbetu .
                    OPTIONAL { ?university rdfs:label ?universityLabel . 
                    FILTER (lang(?universityLabel) = "fr") }
                } LIMIT 1
            }
            BIND(ex:Google(REPLACE("UNIV France ","UNIV",STR(?universityLabel))) AS ?uri)
            BIND(ex:BS4(?uri) AS ?page)   
            BIND(ex:LLMGRAPH(REPLACE("generate in JSON-LD a schema.org representation for a type university of : <page> PAGE </page>. Output only JSON-LD","PAGE",STR(?page)),?uri) AS ?g)
            GRAPH ?g {?uri <http://example.org/has_schema_type> ?o }    
        }
        """

    qres = store.query(query)
    for row in qres:
        print(f"row : {row}")


def dpedia_seg_llmg():
    ##
    ## DBPEDIA + Google (Graph) + LLM (Graph)
    ##
    query="""
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dbr: <http://dbpedia.org/resource/>
        PREFIX ex: <http://example.org/>

        SELECT ?university ?uri ?o1
        WHERE {
            SERVICE <http://dbpedia.org/sparql> {
                SELECT *  WHERE {
                    ?university a dbo:University ;
                        dbo:country dbr:France ;
                        dbo:numberOfStudents ?nbetu .
                    OPTIONAL { ?university rdfs:label ?universityLabel . 
                    FILTER (lang(?universityLabel) = "fr") }
                } LIMIT 1
            }
            BIND(ex:SEGRAPH(REPLACE("UNIV France","UNIV",STR(?universityLabel)),?university) AS ?segraph).
            GRAPH ?segraph {?university <http://example.org/has_uri> ?uri}    

            BIND(ex:BS4(?uri) AS ?page)   
            BIND(ex:LLMGRAPH(REPLACE("generate in JSON-LD a schema.org representation for a type university of : <page> PAGE </page>. Output only JSON-LD","PAGE",STR(?page)),?university) AS ?g)
            GRAPH ?g {?university <http://example.org/has_schema_type> ?root . ?root ?p1 ?o1}    
        }
        """
#    explain(query)
    qres = store.query(query)
    for row in qres:
        for var in qres.vars:  # results.vars contient les noms des variables
            print(f"{var}: {row[var]}")  # Afficher nom de colonne et valeur
        print()  # Séparation entre les lignes
#    for row in qres:
#        print(f"row : {row}")



## If 
## Exception: You performed a query operation requiring a dataset (i.e. ConjunctiveGraph), 
## but operating currently on a single graph.
## -> use store of SPARQLLM and not Graph g=Graph()ss
if __name__ == "__main__":
    local_llmf()
    dbpedia_seg()
    query_sef_llmf()
    dpedia_sef_llmg()
    dpedia_seg_llmg()
    pass