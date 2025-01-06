from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace

import requests
import json
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import result_as_table, is_valid_uri, clean_invalid_uris
import logging
logger = logging.getLogger(__name__)

import os
import re



def set_nested_value(d, key, value):
    keys = re.findall(r'\w+|\[\d+\]', key)  # Sépare les parties avec des indices (ex. x[0], y, z)
    
    temp_dict = d
    for i, k in enumerate(keys[:-1]):  # On parcourt jusqu'à la dernière clé
        if '[' in k:  # Si c'est un index dans une liste
            list_index = int(k[k.find('[')+1:k.find(']')])  # Extrait l'index de la liste
            if len(temp_dict) <= list_index:  # Si la liste n'est pas encore assez grande, on l'agrandit
                temp_dict = temp_dict.setdefault(keys[i-1], [])
                temp_dict = [None] * (list_index + 1)
            temp_dict = temp_dict[list_index]  # Accède à l'élément de la liste
        else:  # Si c'est une clé de dictionnaire
            temp_dict = temp_dict.setdefault(k, {})
    
    # Pour la dernière clé, on affecte la valeur
    last_key = keys[-1]
    if '[' in last_key:  # Si c'est un index dans une liste
        list_index = int(last_key[last_key.find('[')+1:last_key.find(']')])  # Extrait l'index
        if len(temp_dict) <= list_index:  # Si la liste n'est pas encore assez grande, on l'agrandit
            temp_dict = [None] * (list_index + 1)
        temp_dict[list_index] = value  # Affecte la valeur à l'index
    else:  # Si c'est une clé de dictionnaire
        temp_dict[last_key] = value

    return temp_dict


def LLMGRAPHAPI(prompt,uri,model=""):
    global store

    model = str(model)
    print("1")
    config = ConfigSingleton()
    # On va chercher ce dont on a besoin
    print("1")
    api_url = config._models[model]["url"]
    print("2")
    key_prompt = config._models[model]["key_prompt"]
    print(key_prompt)
    timeout = int(config._models[model]["timeout"])
    key_reponse = config._models[model]["key_reponse"]

    # Definition du payload envoyé à l'API
    payload = config._models[model]["payload"]

    # Extraction des clés de la chaîne 'messages[0]["content"]' avec une expression régulière
    keys = re.findall(r'\[([^\]]+)\]|\b([^\[\]]+)\b', key_prompt)

    # Convertir les résultats en une liste de clés
    keys = [k[0] if k[0] else k[1] for k in keys]

    # Naviguer dans le dictionnaire et affecter la nouvelle valeur
    d = payload
    for k in keys[:-1]:  # Parcourir tous sauf le dernier niveau
        if k.isdigit():  # Si la clé est un index de liste
            k = int(k)
        d = d[k]  # Descendre dans la structure

    # Affecter la nouvelle valeur au dernier niveau (content)
    d[keys[-1]] = str(prompt)

    print("payload", payload)



    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"

    logger.debug(f"uri: {uri}, Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}")

    #print(f"LLMGRAPH_OLLAMA  uri: {uri}, Prompt: {prompt[:100]} <...>")

    if not isinstance(uri,URIRef) or not is_valid_uri(uri):
        logger.debug("invalid URI {uri}")
        return URIRef("http://example.org/invalid_uri")


    graph_uri=URIRef(uri)
    named_graph = store.get_context(graph_uri)

    headers = {
        "Authorization": f"Bearer {os.environ.get("OPENAI_API_KEY")}",
        "Content-Type": "application/json"
    }


    # Send the POST request
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 200:
            result = response.json()
        else:
            logger.debug(f"Response Error: {response.status_code}")
            return graph_uri
    except requests.exceptions.RequestException as e:
        logger.debug(f"Request Error: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))
        return graph_uri


    # Extraire les parties de la clé
    keys = re.findall(r'\[([^\]]+)\]|\b([^\[\]]+)\b', key_reponse)
    keys = [k[0] if k[0] else k[1] for k in keys]  # Liste de clés

    # Accéder à la valeur dans le dictionnaire
    d = result
    for k in keys[:-1]:  # Parcourir tous sauf le dernier niveau
        if k.isdigit():  # Si la clé est un indice de liste
            k = int(k)
        d = d[k]  # Descendre dans la structure

    # Extraire la valeur
    jsonld_data = d[keys[-1]]

    try:
        named_graph.parse(data=jsonld_data, format="json-ld")
        clean_invalid_uris(named_graph)
        named_graph.add((uri, URIRef("http://example.org/has_schema_type"), Literal(5, datatype=XSD.integer)))

        #link new triple to bag of mappings
        insert_query_str = f"""
            INSERT  {{
            <{uri}> <http://example.org/has_schema_type> ?subject .}}
                WHERE {{
                    ?subject a ?type .
                }}"""
        named_graph.update(insert_query_str)

        for subj, pred, obj in named_graph:
            logger.debug(f"Sujet: {subj}, Prédicat: {pred}, Objet: {obj}")
    except Exception as e:
        logger.error(f"Error in parsing JSON-LD: {e}")
        named_graph.add((uri, URIRef("http://example.org/has_error"), Literal("Error {e}", datatype=XSD.string)))

    print("graph_uri", graph_uri)
    return graph_uri 


# run with : python -m SPARQLLM.udf.llmgraphAPI
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    config = ConfigSingleton(config_file='config.ini')

    # Register the function with a custom URI
    register_custom_function(URIRef("http://example.org/LLMGRAPHAPI"), LLMGRAPHAPI)

    # store is a global variable for SPARQLLM
    # not good, but see that later...
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # SPARQL query using the custom function
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?o ?p ?x  WHERE {
        BIND(\"\"\"
            A MusicComposition Example. The following JSON-LD models
            the composition A Day in the Life by Lennon and McCartney,
            regardless of who performs or records the song.
         \"\"\" AS ?page)  
        BIND(ex:LLMGRAPHAPI(CONCAT(\"\"\"
            [INST]\\n return as JSON-LD the schema.org representation of text below without formating. 
             \\n[/INST]\"\"\",
            STR(?page)),<http://example.org/myentity>, "SLM-GPT4") AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . 
                    ?o a <http://schema.org/Person> .
                    ?o ?p ?x}    
    }
    """

    # Execute the query
    result = store.query(query_str)

    # Display the results
    print_result_as_table(result)