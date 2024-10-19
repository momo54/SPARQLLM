from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template

from openai import OpenAI
import os
client = OpenAI(
        # This is the default and can be omitted
        api_key=os.environ.get("OPENAI_API_KEY"),
    )


def LLM(prompt):
    #print(f"Prompt: {prompt}")
    # Call OpenAI GPT with bind  _expr
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
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

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/LLM"), LLM)

if __name__ == "__main__":

    # Create a sample RDF graph
    g = Graph()

    # Add some sample data to the graph
    g.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(5, datatype=XSD.integer)))

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
    query = prepareQuery(query_str)
    result = g.query(query)

    # Display the results
    for row in result:
        print(f"Result : {row['result']}")
