from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.plugins.sparql.operators import custom_function
import rdflib.plugins.sparql
from rdflib.plugins.sparql.sparql import QueryContext

import importlib
from rdflib.plugins.sparql import CUSTOM_EVALS
from rdflib.plugins.sparql.evaluate import *
from rdflib.plugins.sparql.algebra import Filter
from rdflib.plugins.sparql import prepareQuery

from rdflib.plugins.sparql.evaluate import evalSelectQuery
import json
from openai import OpenAI
import os

client = OpenAI(
        # This is the default and can be omitted
        api_key=os.environ.get("OPENAI_API_KEY"),
    )

def LLMOPENAI(prompt):


    # Call OpenAI GPT with bind  _expr
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0
    )

    texte = response.choices[0].message.content

    return texte

g = Graph()

# Définir un espace de noms
EX = Namespace("http://example.org/")


def jsonToGraph(graph, json_data):

    for triple in json_data:
        triple_list = list(triple.values())
        g.add((URIRef(triple_list[0]), URIRef(triple_list[1]), Literal(triple_list[2])))


def LLM(dataRDF, dataToRead, prompt):
    finalPrompt = "En te basant sur ce texte: " + dataToRead
    prompt += "\nRépondre en json sans formatage ```json``` au format suivant représentant des triplets rdf et seulement des string: \n[\n"
    for triplet in dataRDF:
        prompt += "{\"" + triplet[0] + "\": valeur, \"" + str(triplet[1]) + "\": "+ str(triplet[1]) + ", \"" + triplet[2] + "\": valeur},"
    prompt += "\n]"
    finalPrompt += prompt
    print("prompt:", finalPrompt)

    response = LLMOPENAI(finalPrompt)
    
    json_data = json.loads(response)

    print("réponse du LLM:", json_data)
    jsonToGraph(g, json_data)
    return json_data




def CustomEval(ctx, part):

    if part.name == "Extend":
        if part.expr.iri == URIRef("http://example.org/LLM"):



            LLM(part.p.triples, part.expr.expr[0], part.expr.expr[1])
            
            ctx[part.var] = part.expr.expr[0].lower()

            return evalExtend(ctx, part)
    
    raise NotImplementedError()



CUSTOM_EVALS['custom_eval'] = CustomEval


# Requête SPARQL pour récupérer les noms et âges
query = """
PREFIX ex: <http://example.org/>

SELECT ?filmTitle ?price ?currency (ex:LLM("Quel sont les informations sur les film de Daniel Radcliffe", "Le film harry potter death hallows coute 5") AS ?reponse)
WHERE {
    ?film ex:name ?filmTitle .
    ?film ex:price ?price .
    ?film ex:currency ?currency
}

"""

# Exécuter la requête
results = g.query(query)

# Afficher les résultats
print("\nRésultats de la requête SPARQL :")
for row in results:
    print(row.filmTitle, "  |  ", row.price, "  |  ", row.currency)