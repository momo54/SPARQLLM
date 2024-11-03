
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import SPARQLLM.udf.funcSE
import SPARQLLM.udf.uri2text
from SPARQLLM.udf.SPARQLLM import store

from llama_cpp import Llama

from llama_cpp.llama import Llama, LlamaGrammar
import httpx
#grammar_text = httpx.get("https://raw.githubusercontent.com/ggerganov/llama.cpp/master/grammars/json_arr.gbnf").text
#grammar = LlamaGrammar.from_string(grammar_text)

#llm = Llama(model_path="/Users/molli-p/SPARQLLM/models/llama-7b.Q8_0.gguf")

import logging

def LLMGRAPH_LLAMA(prompt,uri):
    global store
    logging.debug(f"LLMGRAPH_LLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    if not isinstance(uri,URIRef) :
        raise ValueError("LLMGRAPH_fake 2nd Argument should be an URI")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    #print(f"LLMGRAPH_LLAMA prompt : {prompt}")

    output = llm(
        prompt,
#        max_tokens=512,  # Nombre maximum de tokens à générer
        grammar=grammar,  # Grammaire à utiliser
#        stop=["\n"],    # Arrêter la génération à la fin d'une ligne
#        echo=True       # Inclure le prompt dans la sortie
    )
    jsonld_data = output['choices'][0]['text']
    print(f"LLMGRAMH JSONLD: {jsonld_data}")
    named_graph.parse(data=jsonld_data, format="json-ld")
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


    return graph_uri 
#    return URIRef("http://dbpedia.org/sparql")

# Register the function with a custom URI
register_custom_function(URIRef("http://example.org/LLMGRAPH-LL"), LLMGRAPH_LLAMA)



# run with python -m SPARQLLM.udf.llmgraph_llama
if __name__ == "__main__":

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
        BIND(ex:LLMGRAPH-LL(REPLACE("[INST]\\n return as JSON-LD  the schema.org representation of text below. Only respond with valid JSON-LD. \\n[/INST] PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o }    
    }
    """

    # Execute the query
    result = store.query(query_str)

    for row in result:
        for var in result.vars:  
            print(f"{var}: {row[var]}") 
    print() 
