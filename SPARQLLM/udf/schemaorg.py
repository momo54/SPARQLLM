# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql.operators import register_custom_function
from urllib.parse import urlparse
import os
import json
from bs4 import BeautifulSoup
import requests
import time
from SPARQLLM.utils.utils import is_valid_uri, clean_invalid_uris, print_result_as_table
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
import logging

logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def is_valid_turtle(turtle_data):
    """
    Vérifie si une chaîne de caractères est un RDF Turtle bien formé.

    Args:
        turtle_data (str): Chaîne à vérifier.

    Returns:
        bool: `True` si le Turtle est valide, `False` sinon.
    """
    if not turtle_data.strip():  # Vérification si la chaîne est vide
        logger.error("Empty Turtle data is not valid.")  # Log de l'erreur
        return False

    graph = Graph()  # Création d'un graphe RDF
    try:
        graph.parse(data=turtle_data, format="turtle")  # Tentative de parsing du Turtle
        return True
    except Exception as e:
        logger.error(f"Invalid Turtle data: {e}")  # Log de l'erreur
        return False


def SCHEMAORG(uri, link_to, rdf_store=None, response_override=None):
    """
    Fonction pour récupérer et parser des données JSON-LD ou Turtle depuis une URI.

    Args:
        uri (str): L'URI source.
        link_to (str): L'URI cible pour ajouter des liens RDF.
        rdf_store (rdflib.Dataset, optionnel): store RDF pour les tests. Défaut : `store`.
        response_override (str, optionnel): Réponse simulée pour les tests.

    Returns:
        URIRef: L'URI du graphe nommé.

    Raises:
        ValueError: Si l'URI est invalide ou si une erreur survient lors de la récupération ou du parsing des données.
    """
    # Utilisation du store global si aucun store n'est fourni
    if rdf_store is None:
        global store
        rdf_store = store

    config = ConfigSingleton()  # Récupération de la configuration singleton
    timeout = int(config.config['Requests']['SLM-TIMEOUT'])  # Récupération du timeout
    wait_time = int(config.config['Requests']['SLM-SEARCH-WAIT'])  # Récupération du temps d'attente

    logger.debug(f"Processing URI: {uri}")  # Log de l'URI en cours de traitement

    # Validation de l'URI
    if not is_valid_uri(uri):
        raise ValueError(f"Invalid URI: {uri}")  # Erreur si l'URI est invalide

    if not isinstance(uri, URIRef):
        raise ValueError("Second argument must be a valid URIRef")  # Erreur si l'URI n'est pas un URIRef

    graph_uri = URIRef(uri)  # Création d'un URI pour le graphe
    named_graph = rdf_store.get_context(graph_uri)  # Récupération du graphe nommé

    logger.debug(f"Waiting for {wait_time} seconds...")  # Log du temps d'attente
    time.sleep(wait_time)  # Attente avant de continuer

    if response_override:
        # Utiliser une réponse simulée pour les tests
        response_text = response_override
    else:
        parsed_url = urlparse(uri)  # Parsing de l'URI
        domain = parsed_url.netloc  # Récupération du domaine

        headers = {
            'Accept': 'text/html',
            'User-Agent': 'Mozilla/5.0',
            "Referer": f"https://{domain}"  # En-tête Referer pour la requête
        }

        logger.debug(f"Fetching RDF data from: {uri}")  # Log de la récupération des données

        try:
            response = requests.get(uri, headers=headers, timeout=timeout)  # Envoi de la requête HTTP
            response.raise_for_status()  # Vérification des erreurs HTTP
            response_text = response.text  # Récupération du contenu de la réponse
        except requests.RequestException as e:
            raise ValueError(f"Request error for URI {uri}: {e}")  # Erreur en cas de problème de requête

    # Parser les scripts JSON-LD depuis la réponse
    soup = BeautifulSoup(response_text, 'html.parser')  # Parsing du HTML avec BeautifulSoup
    for script in soup.find_all("script", {"type": "application/ld+json"}):  # Recherche des scripts JSON-LD
        try:
            data = json.loads(script.string)  # Parsing du JSON-LD
            named_graph.parse(data=json.dumps(data), format="json-ld")  # Ajout des données au graphe
            logger.debug(f"Valid JSON-LD script added to graph.")  # Log de l'ajout réussi
        except json.JSONDecodeError:
            logger.warning(f"Skipping invalid JSON-LD: {script.string}")  # Log si le JSON-LD est invalide
        except Exception as e:
            logger.error(f"Error parsing JSON-LD: {e}")  # Log de l'erreur de parsing

    # Vérification et ajout des données Turtle si valides
    if is_valid_turtle(response_text):
        try:
            named_graph.parse(data=response_text, format="turtle")  # Ajout des données Turtle au graphe
            logger.debug("Valid Turtle data added to graph.")  # Log de l'ajout réussi
        except Exception as e:
            logger.error(f"Error parsing Turtle data: {e}")  # Log de l'erreur de parsing
            raise ValueError(f"Error processing RDF data: {e}")  # Erreur en cas de problème de parsing

    try:
        logger.debug(f"Size of named graph: {len(named_graph)}")  # Log de la taille du graphe
        clean_invalid_uris(named_graph)  # Nettoyage des URI invalides

        # Ajouter des triplets RDF
        insert_query_str = f"""
            INSERT {{
                <{link_to}> <http://example.org/has_schema_type> ?subject .
            }}
            WHERE {{
                ?subject a ?type .
            }}
        """
        named_graph.update(insert_query_str)  # Mise à jour du graphe avec la requête SPARQL
    except Exception as e:
        logger.error(f"Error updating named graph: {e}")  # Log de l'erreur de mise à jour

    return graph_uri  # Retourne l'URI du graphe


# Exécution du module avec : python -m SPARQLLM.udf.schemaorg
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/SCHEMAORG"), SCHEMAORG)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"),
               URIRef("http://example.org/hasValue"),
               URIRef("https://zenodo.org/records/13957372")))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?o
    WHERE {
        ?s ?p ?uri .
        BIND(ex:SCHEMAORG(?uri, ?s) AS ?g)
        GRAPH ?g {
            ?s <http://example.org/has_schema_type> ?o .
        }
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)