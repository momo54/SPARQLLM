from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

import requests
import html
import html2text
import unidecode

import logging

# carefull, max_size is a string
def GETTEXT(uri,max_size):
    try:

        headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0'  # En-tête optionnel pour émuler un navigateur
        }

        # Faire la requête HTTP pour obtenir le contenu de la page
        response = requests.get(uri,headers=headers)
        response.raise_for_status()  # Vérifie les erreurs HTTP
        if 'text/html' in response.headers['Content-Type']:

            h = html2text.HTML2Text()
            uri_text = h.handle(response.text)
            uri_text_uni= unidecode.unidecode(uri_text).strip()
            #print(f"Text: {uri_text_uni},max_size={max_size}")
            logging.debug(f"max_size={max_size}")
            max_size = int(max_size)
            return Literal(uri_text_uni[:max_size], datatype=XSD.string)
        else:
            return  Literal("No HTML content at {uri}")

    except requests.exceptions.RequestException as e:
        return  Literal("Error retreiving {uri}")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/GETTEXT"), GETTEXT)


if __name__ == "__main__":

    # Create a sample RDF graph
    g = Graph()

    # Add some sample data to the graph
    g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal("https://zenodo.org/records/13957372")))  

    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        ?s ?p ?uri .
        BIND(ex:GETTEXT(?uri,5000) AS ?t)
    }
    """
    # Execute the query
    query = prepareQuery(query_str)
    result = g.query(query)

    # Display the results
    for row in result:
        print(f"Result : {row}")
