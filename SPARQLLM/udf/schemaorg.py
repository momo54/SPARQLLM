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
import logging

from SPARQLLM.udf.llmgraph_ollama import is_valid_uri,clean_invalid_uris
from SPARQLLM.udf.SPARQLLM import store

from requests_html import HTMLSession



from urllib.parse import urlparse

# carefull, max_size is a string
def SCHEMAORG(uri,link_to):
    global store
    logging.info(f"SCHEMA  uri: {uri}")

    if not is_valid_uri(uri):
        logging.debug("SCHEMA : URI not valid  {uri}")
        return URIRef("http://example.org/invalid_uri")

    if not isinstance(uri,URIRef) :
        raise ValueError("SCHEMA 2nd Argument should be an URI")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

 
    logging.info("SCHEMA Waiting for 5 seconds...")
    time.sleep(5)

    parsed_url = urlparse(uri)
    domain = parsed_url.netloc  # Get the domain (hostname)


    headers = {
        'Accept': 'text/html',
        'User-Agent': 'Mozilla/5.0',  # En-tête optionnel pour émuler un navigateur
        "Referer": f"https://{domain}"
    }

    logging.info(f"SCHEMA : URI: {uri}, headers: {headers}")

    # Récupérer le contenu de la page
#    session = HTMLSession()
#    response = session.get(uri,headers=headers,timeout=20)
    response = requests.get(uri,headers=headers,timeout=20)
    soup = BeautifulSoup(response.text, 'html.parser')
    

    # Trouver tous les scripts de type "application/ld+json"
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            print(f"Script: {type(script.string)}, {script.string}")
            # Charger le contenu JSON
            #data = json.loads(script.string) # test valid json.
            named_graph.parse(data=script.string, format="json-ld")
        except json.JSONDecodeError:
            logging.info(f"SCHEMA : invalid JSON-LD {script.string}")
            continue  # Si le JSON n'est pas valide, ignorer ce script
    
    try:
        logging.info(f"SCHEMA size of JSON-LD: {len(named_graph)}")
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
#            logging.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        print(f"Error in parsing JSON-LD: {e}")

    return graph_uri 


# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/SCHEMAORG"), SCHEMAORG)

## run with : python -m SPARQLLM.udf.schemaorg
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    # Create a sample RDF graph

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

    # Display the results
    for row in result:
        print(f"Result : {row}")
