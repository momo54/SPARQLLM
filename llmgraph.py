
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import funcSE

from openai import OpenAI
import os
client = OpenAI(
        # This is the default and can be omitted
        api_key=os.environ.get("OPENAI_API_KEY"),
    )



def LLMGRAPH(prompt,uri):
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

    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    try:
    # Extract the generated text from the response
        jsonld_data = response.choices[0].message.content
        #print(f"JSONLD: {jsonld_data}")
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

    except Exception as e:
        print(f"LLMGRAPH Parse Error: {e}")

    return graph_uri 

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/LLMGRAPH"), LLMGRAPH)

## super important !!
store = ConjunctiveGraph()


if __name__ == "__main__":

    # Add some sample data to the graph
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?o ?p1 ?o1  WHERE {
        ?s ?p ?uri .
        BIND(ex:BS4(?uri) AS ?page)  
        BIND(ex:LLMGRAPH(REPLACE("Extrait en JSON-LD la représentation schema.org de : PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . ?o ?p1 ?o1}    
    }
    """

    # Execute the query
    query = prepareQuery(query_str)
    result = store.query(query)

    # Display the results
    for row in result:
        print(f"row : {row}")
