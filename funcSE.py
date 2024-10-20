from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

# https://console.cloud.google.com/apis/api/customsearch.googleapis.com/cost?hl=fr&project=sobike44
se_api_key=os.environ.get("SEARCH_API_SOBIKE44")
se_cx_key=os.environ.get("SEARCH_CX")

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode

headers = {
    'Accept': 'text/html',
    'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
}

def BS4(uri):
    try:
        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri,headers=headers)
        response.raise_for_status()  # Vérifie les erreurs HTTP
        if 'text/html' in response.headers['Content-Type']:

            h = html2text.HTML2Text()
            text = h.handle(response.text)
            text = unidecode.unidecode(text)
            return Literal(text.strip()[:5000])
        else:
            return  Literal("No HTML content at {uri}")

    except requests.exceptions.RequestException as e:
        # En cas d'erreur HTTP ou de connexion
        print(f"Erreur lors de la requête : {e}")
        return  Literal("Error retreiving {uri}")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/BS4"), BS4)


# Carefull to return the good types !!
def Google(keywords):

    se_url=f"https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}"

    # Send the request to Google search
    se_url = f"{se_url}&q={quote(keywords)}"
    # print(f"se_url={se_url}")
    headers = {'Accept': 'application/json'}
    request = Request(se_url, headers=headers)
    response = urlopen(request)
    json_data = json.loads(response.read().decode('utf-8'))

    # Extract the URLs from the response
    links = [item['link'] for item in json_data.get('items', [])]
    return URIRef(links[0]) 

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/Google"), Google)

if __name__ == "__main__":

    # Create a sample RDF graph
    g = Graph()

    # Add some sample data to the graph
    g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("univ nantes", datatype=XSD.string)))  

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("trouve moi une url pour UNIV ","UNIV",STR(?value))) AS ?result)
    }
    """

    # Execute the query
    query = prepareQuery(query_str)
    result = g.query(query)

    # Display the results
    for row in result:
        print(f"Result : {row['result']}")

        # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:Google(REPLACE("Je veux savoir le nombre d'étudiants à UNIV ","UNIV",STR(?value))) AS ?uri)
        BIND(ex:BS4(?uri) AS ?result)
    }
    """
    # Execute the query
    query = prepareQuery(query_str)
    result = g.query(query)

    # Display the results
    for row in result:
        print(f"Result : {row['result']}")
