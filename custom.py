import rdflib
from rdflib.namespace import FOAF, RDF, RDFS
from rdflib.plugins.sparql.evaluate import evalBGP
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, FOAF

from rdflib.plugins.sparql.evaluate import evalServiceQuery
from serviceLLM import evalServiceLLMQuery
from serviceSE import evalServiceSEQuery

import funcSE 
import funcLLM 
import llmgraph
import segraph

def customEval(ctx, part):  # noqa: N802
    """
    Rewrite triple patterns to get super-classes
    """
    #print("part.name", part.name)
    if part.name == "ServiceGraphPattern":
        #print(f"service term :{part.get('term')}")
        if str(part.get('term')) == "http://chat.openai.com":
            return evalServiceLLMQuery(ctx, part)
        elif str(part.get('term')) == "http://www.google.com":
            return evalServiceSEQuery(ctx, part)
        else:
            return evalServiceQuery(ctx, part)
    raise NotImplementedError()

rdflib.plugins.sparql.CUSTOM_EVALS["exampleEval"] = customEval

if __name__ == "__main__":


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
