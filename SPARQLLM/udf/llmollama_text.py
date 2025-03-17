
import json
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
import rdflib.plugins.sparql.operators as operators
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace
from rdflib import URIRef

import requests
from string import Template


import bs4
from SPARQLLM.udf.uri2text import GETTEXT
from SPARQLLM.udf.readfile import readhtmlfile

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, is_valid_uri, clean_invalid_uris

import logging
logger = logging.getLogger(__name__)

def llmollama_text(prompt):
    """
        Sends a prompt to the OLLAMA API, retrieves the response, and returns it as an RDF Literal.

        Args:
            prompt (str): The text prompt to send to the OLLAMA API.

        Returns:
            Literal: The response from the OLLAMA API as an RDF Literal. If an error occurs, returns an error message as an RDF Literal.
    """
    global store

    config = ConfigSingleton()
    api_url = config.config['Requests']['SLM-OLLAMA-URL']
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])
    model = config.config['Requests']['SLM-OLLAMA-MODEL']

    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"
    logger.debug(f"Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")

    # Set up the request payload
    payload = {
        "model": model,
        "prompt": str(prompt),
        "stream": False,
    }

    # Send the POST request
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        data = response.json()
#        logger.debug(f"Response: {json.dumps(data, indent=2)}")
        if response.status_code == 200:            
            result = data.get("response")
        else:
            logger.debug(f"Response Error: {response.status_code}")
            return Literal(f"error: {response.reason}")
    except requests.exceptions.RequestException as e:
        logger.debug(f"Request Error: {e}")
        return Literal(f"error: {e}")
    logger.debug(f"Result: {result}")
    return Literal(result)

