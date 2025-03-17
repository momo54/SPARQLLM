
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

config = ConfigSingleton()
model = config.config['Requests']['SLM-OPENAI-MODEL']

api_key = os.environ.get("OPENAI_API_KEY", "default-api-key")
client = OpenAI(api_key=api_key)

def llm_graph_openai(prompt,uri):
    """
        Generates a named graph in an RDF store using OpenAI's GPT model based on a given prompt.

        Args:
            prompt (str): The prompt to be sent to the OpenAI GPT model.
            uri (str): The URI of the named graph to be created.

        Returns:
            URIRef: The URI of the created named graph.

        Raises:
            ValueError: If the OpenAI API key is not set.
    """
    global store

    assert model != "", "OpenAI Model not set in config.ini"
    if api_key == "default-api-key":
        raise ValueError("OPENAI_API_KEY is not set. Using default value, which may not work for real API calls.")

    logger.debug(f"uri: {uri}, model: {model}, Prompt: {prompt[:50]} <...>")


    graph_name = prompt + ":"+str(uri)
    graph_uri = URIRef("http://mistral.org/"+hashlib.sha256(graph_name.encode()).hexdigest())
    if  named_graph_exists(store, graph_uri):
        logger.debug(f"Graph {graph_uri} already exists (good)")
        return graph_uri
    else:
        named_graph = store.get_context(graph_uri)


    # Call OpenAI GPT with bind  _expr
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

    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    try:
        jsonld_data = response.choices[0].message.content
        named_graph.parse(data=jsonld_data, format="json-ld")

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
                <{uri}> <http://example.org/has_schema_type> ?subject .}}
            WHERE {{
                ?subject a ?type .
            }}"""
        named_graph.update(insert_query_str)

        res=named_graph.query("""SELECT ?s ?o WHERE { ?s <http://example.org/has_schema_type> ?o }""")

    except Exception as e:
        logger.error(f"Error in parsing JSON-LD: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))

    return graph_uri 



