
import hashlib
import random
import time
import warnings
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import clean_invalid_uris, named_graph_exists, print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)

from mistralai import Mistral
import os

config = ConfigSingleton()
model = config.config.get('Requests', 'SLM-MISTRALAI-MODEL', fallback='ministral-8b-latest')
api_key = os.environ.get("MISTRAL_API_KEY", "default-api-key")
client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY", api_key))

def call_mistral_api(client, model, prompt, max_retries=5):
    """Appelle l'API Mistral avec gestion des erreurs 429 (trop de requêtes)."""
    retry_delay = 1  # Délai initial en secondes
    time.sleep(retry_delay)
    for attempt in range(max_retries):
        try:
            chat_response = client.chat.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return chat_response  # Succès, on retourne la réponse

        except Exception as e:
            if "429" in str(e) or "Rate limit" in str(e):
                logger.warning(f"Rate limit exceeded. Retrying in {retry_delay} seconds... (attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)  # Attendre avant de réessayer
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Error in calling Mistral API: {e}")
                raise ValueError(f"Error in calling Mistral API: {e}")

    raise ValueError("Max retries exceeded. Mistral API is still returning 429.")

def llm_graph_mistral(prompt,uri):
    global store

    if api_key == "default-api-key":
        raise ValueError("MISTRAL_API_KEY is not set. Using default value, which may not work for real API calls.")

    logger.debug(f"uri: {uri}, model: {model}, Prompt: {prompt[:50]} <...>")

    graph_name = prompt + ":"+str(uri)
    graph_uri = URIRef("http://mistral.org/"+hashlib.sha256(graph_name.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:
        named_graph = store.get_context(graph_uri)

    chat_response = call_mistral_api(client, model, "Ton prompt ici")

    # try:
    #     chat_response = client.chat.complete(
    #         model= model,
    #         messages = [
    #             {
    #                 "role": "user",
    #                 "content": prompt,
    #             },
    #         ]
    #     )   
    # except Exception as e:
    #     logger.error(f"Error in calling Mistral API: {e}")
    #     raise ValueError(f"Error in calling Mistral API: {e}")
    jsonld_data = chat_response.choices[0].message.content
    logger.debug(f"JSON-LD data: {jsonld_data[:100]} <...>")
#    logger.debug(f"JSON-LD data: ({jsonld_data})")

    try:
        named_graph.parse(data=jsonld_data, format="json-ld")
        clean_invalid_uris(named_graph)

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
                <{uri}> <http://example.org/has_schema_type> ?subject .}}
            WHERE {{
                ?subject a ?type .
            }}"""
        named_graph.update(insert_query_str)


    except Exception as e:
        logger.error(f"Error in parsing JSON-LD: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal(f"Error {e}", datatype=XSD.string)))

    return graph_uri 



