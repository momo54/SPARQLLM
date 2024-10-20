from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode,quote
from urllib.request import Request, urlopen

import os
import json

from bs4 import BeautifulSoup
import requests
import html
import html2text
import unidecode



def SCRAP(uri):
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
register_custom_function(URIRef("http://example.org/SCRAP"), SCRAP)
