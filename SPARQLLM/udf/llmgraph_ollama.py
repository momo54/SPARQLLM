
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
from urllib.parse import urlencode,quote

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import SPARQLLM.udf.funcSE
import SPARQLLM.udf.uri2text
from SPARQLLM.udf.SPARQLLM import store


import logging

import requests
# Define the API endpoint
api_url = "http://localhost:11434/api/generate"

from rdflib import URIRef
from urllib.parse import urlparse

def is_valid_uri(uri):
    parsed_uri = urlparse(str(uri))
    # Check if the URI has a valid scheme and netloc
    return all([parsed_uri.scheme, parsed_uri.netloc])

def clean_invalid_uris(graph):
    to_remove = []
    
    for s, p, o in graph:
        # Check each term for URI validity
        if (isinstance(s, URIRef) and not is_valid_uri(s)) or \
           (isinstance(p, URIRef) and not is_valid_uri(p)) or \
           (isinstance(o, URIRef) and isinstance(o, URIRef) and not is_valid_uri(o)):
            to_remove.append((s, p, o))
    
    # Remove invalid triples
    for triple in to_remove:
        graph.remove(triple)


def LLMGRAPH_OLLAMA(prompt,uri):
    global store
    logging.info(f"LLMGRAPH_OLLAMA  uri: {uri}")
    logging.debug(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    #print(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    if not is_valid_uri(uri):
        logging.debug("LLMGRAPH_OLLAMA : URI not valid  {uri}")
        return URIRef("http://example.org/invalid_uri")

    if not isinstance(uri,URIRef) :
        raise ValueError("LLMGRAPH_OLLAMA 2nd Argument should be an URI")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    #print(f"LLMGRAPH_OLLAMA prompt : {prompt}")

    model="llama3.1:latest" #8B
    #model="llama3.2:latest" # 3B

    # Set up the request payload
    payload = {
        "model": model,
        "prompt": str(prompt),
        "format": "json",
        "stream": False,
    }

    #print(f"OLLAMA Payload: {payload}")

    # Send the POST request
    try:
        response = requests.post(api_url, json=payload, timeout=20)
        if response.status_code == 200:
            # Parse and print the response
    #        print(f"OLLAMA Response: {response.text}")
            result = response.json()
            logging.debug(f"LLMGRAPH_OLLAMA: {result['response']}")
        else:
            logging.debug(f"LLMGRAPH_OLLAMA: Error: {response.status_code}")
            return graph_uri 
    except requests.exceptions.RequestException as e:
        logging.debug(f"LLMGRAPH_OLLAMA: Error: {e}")
        return graph_uri

#    jsonld_data = result['message']['content']
    jsonld_data = result['response']
    #print(f"LLMGRAMH JSONLD: {jsonld_data}")
    try:
        named_graph.parse(data=jsonld_data, format="json-ld")
        clean_invalid_uris(named_graph)
        # Example usage to filter out invalid URIs


        #print(f"LLMGRAPH parse JSONLD_ok")

        named_graph.add((uri, URIRef("http://example.org/has_schema_type"), Literal(5, datatype=XSD.integer)))

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
            <{uri}> <http://example.org/has_schema_type> ?subject .}}
                WHERE {{
                    ?subject a ?type .
                }}"""
            # #print(f"Query: {insert_query_str}")
        named_graph.update(insert_query_str)

        for subj, pred, obj in named_graph:
            logging.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        print(f"Error in parsing JSON-LD: {e}")

    return graph_uri 
#    return URIRef("http://dbpedia.org/sparql")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/LLMGRAPH-OLLA"), LLMGRAPH_OLLAMA)



# OLLAMA server should be running
# run with : python -m SPARQLLM.udf.llmgraph_ollama
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # store is a global variable for SPARQLLM
    # not good, but see that later...
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?s ?uri ?o  WHERE {
        {
            SELECT ?s ?uri WHERE {
                ?s ?p ?uri .
            }
        }
        BIND(ex:GETTEXT(?uri,1000) AS ?page)  
        BIND(ex:LLMGRAPH-OLLA(REPLACE("[INST]\\n return as JSON-LD  the schema.org representation of text below. Only respond with valid JSON-LD. \\n[/INST] PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o }    
    }
    """

    # Execute the query
    result = store.query(query_str)

    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}") 
    print() 
