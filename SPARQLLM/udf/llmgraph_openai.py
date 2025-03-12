import hashlib
import warnings
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)

from openai import OpenAI
import os

# Configuration singleton to access configuration settings
config = ConfigSingleton()
# Retrieve the model name from the configuration
model = config.config['Requests']['SLM-OPENAI-MODEL']

# Retrieve the API key from the environment variables, with a default value
api_key = os.environ.get("OPENAI_API_KEY", "default-api-key")
# Initialize the OpenAI client with the API key
client = OpenAI(api_key=api_key)

def llm_graph_openai(prompt, uri):
    """
    Processes a given prompt using the OpenAI API and updates a named graph with the response.

    Args:
        prompt (str): The prompt to be sent to the OpenAI API.
        uri (str): The URI of an entity to link to.

    Returns:
        URIRef: The URI of the new fresh immutable named graph.

    Raises:
        ValueError: If the API key is not set.
    """
    global store

    # Ensure the model is set in the configuration
    assert model != "", "OpenAI Model not set in config.ini"
    # Check if the API key is set to the default value
    if api_key == "default-api-key":
        raise ValueError("OPENAI_API_KEY is not set. Using default value, which may not work for real API calls.")

    # Log the URI, model, and a truncated version of the prompt for debugging
    logger.debug(f"uri: {uri}, model: {model}, Prompt: {prompt[:50]} <...>")

    # Create a unique graph name and URI based on the prompt and URI
    graph_name = prompt + ":" + str(uri)
    graph_uri = URIRef("http://mistral.org/" + hashlib.sha256(graph_name.encode()).hexdigest())

    # Check if the named graph already exists in the store
    if named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:
        # Get the context for the named graph
        named_graph = store.get_context(graph_uri)

    # Call OpenAI GPT with the prompt
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0
    )

    # Use the provided URI as the graph URI
    graph_uri = URIRef(uri)
    named_graph = store.get_context(graph_uri)

    try:
        # Extract the JSON-LD data from the response
        jsonld_data = response.choices[0].message.content
        # Parse the JSON-LD data into the named graph
        named_graph.parse(data=jsonld_data, format="json-ld")

        # Link new triples to the bag of mappings
        insert_query_str = f"""
            INSERT  {{
                <{uri}> <http://example.org/has_schema_type> ?subject .}}
            WHERE {{
                ?subject a ?type .
            }}"""
        named_graph.update(insert_query_str)

        # Execute a query to retrieve the subjects and objects of the new triples
        res = named_graph.query("""SELECT ?s ?o WHERE { ?s <http://example.org/has_schema_type> ?o }""")

    except Exception as e:
        # Log any errors that occur during parsing
        logger.error(f"Error in parsing JSON-LD: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal(f"Error {e}", datatype=XSD.string)))

    return graph_uri