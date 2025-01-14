# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function
import rdflib.plugins.sparql.operators as operators
from rdflib import Graph, ConjunctiveGraph, URIRef, Literal, Namespace
from rdflib import URIRef

import requests
from string import Template

import SPARQLLM.udf.funcSE
from SPARQLLM.udf.uri2text import GETTEXT
from SPARQLLM.udf.readfile import readhtmlfile

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table, is_valid_uri, clean_invalid_uris

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def LLMGRAPH_OLLAMA(prompt, uri):
    """
    Fonction pour interagir avec un modèle de langage OLLAMA et stocker les résultats dans un graphe RDF.

    Args:
        prompt (str): Le texte d'entrée (prompt) à envoyer au modèle.
        uri (URIRef): L'URI du graphe RDF où stocker les résultats.

    Returns:
        URIRef: L'URI du graphe RDF contenant les résultats ou un URI d'erreur en cas de problème.

    Raises:
        AssertionError: Si les configurations requises ne sont pas définies ou si le prompt est vide.
        requests.exceptions.Timeout: En cas de dépassement du délai d'attente.
    """
    global store

    config = ConfigSingleton()  # Récupération de la configuration singleton
    api_url = config.config['Requests']['SLM-OLLAMA-URL']  # URL de l'API OLLAMA
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Délai d'attente pour la requête
    model = config.config['Requests']['SLM-OLLAMA-MODEL']  # Modèle OLLAMA à utiliser

    # Vérifications des configurations
    assert api_url != "", "OLLAMA API URL not set in config.ini"
    assert model != "", "OLLAMA Model not set in config.ini"
    assert timeout > 0, "OLLAMA Timeout not defined nor positive"
    assert prompt != "", "Prompt is empty"
    assert store is not None, "Store is not defined"

    logger.debug(f"uri: {uri}, Prompt: {prompt[:100]} <...>, API: {api_url}, Timeout: {timeout}, Model: {model}")  # Log des informations

    # Vérification de la validité de l'URI
    if not isinstance(uri, URIRef) or not is_valid_uri(uri):
        logger.debug(f"Invalid URI: {uri}")
        return URIRef("http://example.org/invalid_uri")

    graph_uri = URIRef(uri)  # Création d'un URI pour le graphe
    named_graph = store.get_context(graph_uri)  # Récupération du graphe nommé

    # Construction de la requête API
    payload = {
        "model": model,  # Modèle à utiliser
        "prompt": str(prompt),  # Prompt à envoyer
        "format": "json",  # Format de réponse attendu
        "stream": False,  # Désactivation du streaming
    }

    try:
        response = requests.post(api_url, json=payload, timeout=timeout)  # Envoi de la requête
        response.raise_for_status()  # Vérification des erreurs HTTP

        if response.status_code == 200:
            jsonld_data = response.json()['response']
        else:
            named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                             Literal(f"API Error: {response.status_code}", datatype=XSD.string)))  # Ajout d'une erreur au graphe
            return graph_uri

    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error: {e}")  # Log de l'erreur de timeout
        named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                         Literal("Timeout Error", datatype=XSD.string)))  # Ajout d'une erreur au graphe
        raise  # Relance l'exception

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")  # Log de l'erreur de requête
        named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                         Literal(f"Request Error: {str(e)}", datatype=XSD.string)))  # Ajout d'une erreur au graphe
        return graph_uri

    # Traitement du JSON-LD
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
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout error: {e}")  # Log de l'erreur de timeout
        raise  # Relance l'exception
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")  # Log de l'erreur de requête
        named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                        Literal(f"Request Error: {str(e)}", datatype=XSD.string)))  # Ajout d'une erreur au graphe
    return graph_uri


# Le serveur OLLAMA doit être en cours d'exécution
# Exécution du module avec : python -m SPARQLLM.udf.llmgraph_ollama
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/LLMGRAPH-OLLA"), LLMGRAPH_OLLAMA)

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?o ?p ?x  WHERE {
        BIND(\"\"\"
            A MusicComposition Example. The following JSON-LD models
            the composition A Day in the Life by Lennon and McCartney,
            regardless of who performs or records the song.
         \"\"\" AS ?page)  
        BIND(ex:LLMGRAPH-OLLA(CONCAT(\"\"\"
            [INST]\\n return as JSON-LD  the schema.org representation of text below. 
            Only respond with valid JSON-LD. \\n[/INST]\"\"\",
            STR(?page)),<http://example.org/myentity>) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . 
                    ?o a <http://schema.org/Person> .
                    ?o ?p ?x}    
    }
    """

    # Exécution de la requête
    result = store.query(query_str)
    print_result_as_table(result)  # Affichage des résultats sous forme de tableau