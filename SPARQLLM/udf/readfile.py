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
from urllib.parse import urlparse


from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

import logging
logger = logging.getLogger(__name__)

# carefull, max_size is a string
import re  # Import nécessaire pour le nettoyage

def readhtmlfile(path_uri, max_size):
    config = ConfigSingleton()  # Mocké dans les tests
    max_size = int(max_size)

    logger.debug(f"uri: {path_uri}, max_size: {max_size}")
    try:
        with open(urlparse(path_uri).path, 'r') as file:
            data = file.read()
            h = html2text.HTML2Text()
            h.ignore_links = True  # Ignore les liens
            h.ignore_images = True  # Ignore les images
            uri_text = h.handle(data)

            # Nettoyage des liens Markdown résiduels (par exemple, "Link")
            uri_text_cleaned = re.sub(r"Link\s*$", "", uri_text)  # Supprime les mots "Link" isolés
            uri_text_cleaned = re.sub(r"\[.*?\]\(.*?\)", "", uri_text_cleaned)  # Supprime les liens Markdown
            
            # Nettoyage général : espaces, nouvelles lignes
            uri_text_cleaned = (
                unidecode.unidecode(uri_text_cleaned)
                .lstrip("#")  # Supprime les symboles Markdown au début
                .replace("\n", " ")  # Remplace les nouvelles lignes par des espaces
                .replace("  ", " ")  # Supprime les espaces multiples
                .strip()
            )

            logger.debug(f"result={uri_text_cleaned[:max_size]}")
            return Literal(uri_text_cleaned[:max_size], datatype=XSD.string)
    except (FileNotFoundError, PermissionError) as e:
        return Literal(f"Error reading {path_uri}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Literal(f"Error reading {path_uri}")



# run with : python -m SPARQLLM.udf.readfile
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/FILE-HTML"), readhtmlfile)


    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        BIND("data/zenodo.html" AS ?uri)
        BIND(ex:FILE-HTML(?uri,100) AS ?t)
    }
    """
    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)