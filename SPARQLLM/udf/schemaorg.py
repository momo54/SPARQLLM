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


import time 

from SPARQLLM.utils.utils import is_valid_uri,clean_invalid_uris
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

#from requests_html import HTMLSession

from urllib.parse import urlparse

import logging
logger = logging.getLogger(__name__)

# carefull, max_size is a string
def SCHEMAORG(uri,link_to):
    global store

    config = ConfigSingleton()
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])

    logger.debug(f"uri: {uri}")

    if not is_valid_uri(uri):
        logger.debug("URI not valid  {uri}")
        return URIRef("http://example.org/invalid_uri")

    if not isinstance(uri,URIRef) :
        raise ValueError("SCHEMA 2nd Argument should be an URI")

    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

 
    logger.debug(f"SCHEMA Waiting for {wait_time} seconds...")
    time.sleep(wait_time)

    parsed_url = urlparse(uri)
    domain = parsed_url.netloc  # Get the domain (hostname)

    headers = {
        'Accept': 'text/html',
        'User-Agent': 'Mozilla/5.0',  # En-tête optionnel pour émuler un navigateur
        "Referer": f"https://{domain}"
    }

    logger.debug(f"URI: {uri}, headers: {headers}")

    # Récupérer le contenu de la page
#    session = HTMLSession()
#    response = session.get(uri,headers=headers,timeout=20)
    response = requests.get(uri,headers=headers,timeout=timeout)
    soup = BeautifulSoup(response.text, 'html.parser')
    

    # Trouver tous les scripts de type "application/ld+json"
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            print(f"Script: {type(script.string)}, {script.string}")
            # Charger le contenu JSON
            #data = json.loads(script.string) # test valid json.
            named_graph.parse(data=script.string, format="json-ld")
        except json.JSONDecodeError:
            logger.debug(f"invalid JSON-LD {script.string}")
            continue  # Si le JSON n'est pas valide, ignorer ce script
    
    try:
        logger.debug(f"size of JSON-LD: {len(named_graph)}")
        clean_invalid_uris(named_graph)

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
            <{link_to}> <http://example.org/has_schema_type> ?subject .}}
                WHERE {{
                    ?subject a ?type .
                }}"""
            # #print(f"Query: {insert_query_str}")
        named_graph.update(insert_query_str)

#        for subj, pred, obj in named_graph:
#            logger.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        logger.error(f"Error in parsing JSON-LD: {e}")

    return graph_uri 



## run with : python -m SPARQLLM.udf.schemaorg
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/SCHEMAORG"), SCHEMAORG)


    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13957372")))  

    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?o
    WHERE {
        ?s ?p ?uri .
        BIND(ex:SCHEMAORG(?uri,?s) AS ?g)
        graph ?g {?s <http://example.org/has_schema_type> ?o }
    }
    """
    # Execute the query
    result = store.query(query_str)
    print_result_as_table(result)
