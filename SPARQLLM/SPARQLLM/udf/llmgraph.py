# Importation des modules nécessaires
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
import json

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module

from openai import OpenAI
import os

# Initialisation du client OpenAI
client = OpenAI(
    # La clé API est récupérée depuis les variables d'environnement
    api_key=os.environ.get("OPENAI_API_KEY"),
)

import json
from rdflib import Graph, URIRef, Literal, RDF


def LLMGRAPH(prompt, uri, response_override=None):
    """
    Fonction pour interagir avec un modèle de langage OpenAI et stocker les résultats dans un graphe RDF.

    Args:
        prompt (str): Le texte d'entrée (prompt) à envoyer au modèle.
        uri (URIRef): L'URI du graphe RDF où stocker les résultats.
        response_override (str, optional): Une réponse simulée à utiliser à la place de l'appel API. Par défaut à None.

    Returns:
        URIRef: L'URI du graphe RDF contenant les résultats.

    Raises:
        ValueError: Si l'URI n'est pas valide ou si une erreur survient lors du traitement des données RDF.
    """
    global store

    config = ConfigSingleton()  # Récupération de la configuration singleton
    model = config.config['Requests']['SLM-OPENAI-MODEL']  # Récupération du modèle OpenAI depuis la configuration
    assert model != "", "OpenAI Model not set in config.ini"  # Vérification que le modèle est configuré

    logger.debug(f"uri: {uri}, model: {model}, Prompt: {prompt[:50]} <...>")  # Log des informations

    # Vérification que l'URI est bien une instance de URIRef
    if not isinstance(uri, URIRef):
        raise ValueError("LLMGRAPH 2nd Argument should be an URI")

    # Utiliser une réponse simulée si fournie, sinon appeler l'API
    if response_override:
        response_content = response_override  # Utilisation de la réponse simulée
    else:
        # Appel à l'API OpenAI pour générer une réponse
        response = client.chat.completions.create(
            model=model,  # Modèle à utiliser
            messages=[
                {
                    "role": "user",  # Rôle de l'utilisateur
                    "content": prompt  # Contenu du prompt
                }
            ],
            temperature=0.0  # Température pour contrôler la créativité (0.0 pour des réponses déterministes)
        )
        response_content = response.choices[0].message.content  # Extraction du texte généré
        print(response_content)

    graph_uri = URIRef(uri)  # Création d'un URI pour le graphe
    named_graph = store.get_context(graph_uri)  # Récupération du graphe nommé

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
        logger.error(f"Error processing RDF data: {e}")  # Log de l'erreur
        raise ValueError(f"Parse Error: {e}")  # Relance de l'exception avec un message d'erreur

    return graph_uri  # Retourne l'URI du graphe


# Exécution du module avec : python -m SPARQLLM.udf.llmgraph
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/LLMGRAPH"), LLMGRAPH)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("https://zenodo.org/records/13955291")))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?o ?p1 ?o1  WHERE {
        {
            SELECT ?s ?uri WHERE {
                ?s ?p ?uri .
            }
        }
        BIND(ex:SLM-BS4(?uri) AS ?page)  
        BIND(ex:LLMGRAPH(REPLACE("Répondre qu'en JSON-LD sans formatage ```json```, Extrait en JSON-LD sans formatage la représentation schema.org de : PAGE ","PAGE",STR(?page)),?uri) AS ?g)
        GRAPH ?g {?uri <http://example.org/has_schema_type> ?o . ?o ?p1 ?o1}    
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)