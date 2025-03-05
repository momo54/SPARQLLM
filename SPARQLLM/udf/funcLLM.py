from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.udf.llmgraph import get_openai_api_key
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)



from openai import OpenAI
import os

client = OpenAI(api_key=get_openai_api_key(),)


def LLM(prompt):
    config = ConfigSingleton()
    model = config.config['Requests']['SLM-OPENAI-MODEL']
    assert model != "", "OpenAI Model not set in config.ini"
    logger.debug(f"prompt: {prompt}, model: {model}")
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
    
    # Extract the generated text from the response
    generated_text = response.choices[0].message.content
    return Literal(generated_text) 

# run with : python -m SPARQLLM.udf.funcLLM 
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/LLM"), LLM)


    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(5, datatype=XSD.integer)))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:LLM(REPLACE("NOMBRE est plus grand que ?","NOMBRE",STR(?value))) AS ?result)
    }
    """

    # Execute the query
    result = store.query(query_str)

    # Display the results
    print_result_as_table(result)
