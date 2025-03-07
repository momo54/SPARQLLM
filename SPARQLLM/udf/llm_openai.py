from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template

from SPARQLLM.config import ConfigSingleton
from llmgraph_openai import get_openai_api_key
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)



from openai import OpenAI
import os

config = ConfigSingleton()
model = config.config['Requests']['SLM-OPENAI-MODEL']

api_key = os.environ.get("OPENAI_API_KEY", "default-api-key")
client = OpenAI(api_key=get_openai_api_key(),)

def llm_openai(prompt):
    assert model != "", "OpenAI Model not set"
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

