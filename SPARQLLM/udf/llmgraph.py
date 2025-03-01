
import warnings
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import SPARQLLM.udf.funcSE
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)

from openai import OpenAI
import os


def get_openai_api_key():
    """Retrieve the OpenAI API key with a default value and a warning if not set."""
    api_key = os.environ.get("OPENAI_API_KEY", "default-api-key")
    if api_key == "default-api-key":
        warnings.warn("OPENAI_API_KEY is not set. Using default value, which may not work for real API calls.")
    return api_key

client = OpenAI(api_key=get_openai_api_key(),)

def LLMGRAPH(prompt,uri):
    global store

    config = ConfigSingleton()
    model = config.config['Requests']['SLM-OPENAI-MODEL']
    assert model != "", "OpenAI Model not set in config.ini"

    logger.debug(f"uri: {uri}, model: {model}, Prompt: {prompt[:50]} <...>")
    for g in store.contexts():  # context() retourne tous les named graphs
        logger.debug(f"LLMGRAPH store named graphs: {g.identifier}")

    if not isinstance(uri,URIRef) :
        raise ValueError("LLMGRAPH 2nd Argument should be an URI")

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
        #print(f"Query: {insert_query_str}")
        named_graph.update(insert_query_str)

        res=named_graph.query("""SELECT ?s ?o WHERE { ?s <http://example.org/has_schema_type> ?o }""")
        for row in res:
            logger.debug(f"existing types in JSON-LD: {row}")
        for g in store.contexts():  # context() retourne tous les named graphs
            logger.debug(f"store graphs: {g.identifier}, len {g.__len__()}")

    except Exception as e:
        raise ValueError(f"Parse Error: {e}")

    return graph_uri 



# run with : python -m SPARQLLM.udf.llmgraph 
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/LLMGRAPH"), LLMGRAPH)

    # store is a global variable for SPARQLLM
    # not good, but see that later...
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?o ?p1 ?o1  WHERE {
        {
            SELECT ?s ?uri WHERE {
                ?s ?p ?uri .
            }
        }
        BIND(ex:BS4(?uri) AS ?page)  
        BIND(ex:LLMGRAPH(REPLACE("Extrait en JSON-LD la représentation schema.org de : PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . ?o ?p1 ?o1}    
    }
    """

    # Execute the query
    result = store.query(query_str)

    # Display the results
    print_result_as_table(result)
