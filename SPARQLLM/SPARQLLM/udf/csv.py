# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.utils.utils import print_result_as_table, named_graph_exists

import os
import json

import pandas as pd
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD

import traceback

import logging

# Configuration du logger pour ce module
logger = logging.getLogger("csv")


def slm_csv(file_url):
    """
    Fonction pour lire un fichier CSV et le convertir en graphe RDF.

    Args:
        file_url (str): L'URL ou le chemin du fichier CSV à lire.

    Returns:
        URIRef: L'URI du graphe RDF créé, ou None en cas d'erreur.
    """
    logger.debug(f"{file_url}, {type(file_url)}")  # Log de l'URL du fichier et de son type
    try:
        df = pd.read_csv(str(file_url))  # Lecture du fichier CSV dans un DataFrame

        # Initialisation du graphe RDF
        n = Namespace("http://example.org/")

        # Définition d'une classe générique pour les enregistrements CSV
        Record = URIRef(n.Record)

        graph_uri = URIRef(file_url)  # Création d'un URI pour le graphe
        if named_graph_exists(store, graph_uri):  # Vérification si le graphe existe déjà
            logger.debug(f"Graph {graph_uri} already exists (good)")
            return None
        else:
            named_graph = store.get_context(graph_uri)  # Création d'un nouveau graphe nommé

        # Création des propriétés pour chaque colonne du CSV
        properties = {col: URIRef(n[col]) for col in df.columns}

        # Ajout des triplets au graphe
        for index, row in df.iterrows():
            # Création d'un URI unique pour chaque enregistrement
            record_uri = URIRef(n[f"record_{index}"])
            named_graph.add((record_uri, RDF.type, Record))  # Ajout du type d'enregistrement

            # Ajout des propriétés pour chaque colonne
            for col, value in row.items():
                if pd.notna(value):  # Vérification des valeurs non nulles
                    # Détermination du type de données approprié
                    if isinstance(value, int):
                        datatype = XSD.integer
                    elif isinstance(value, float):
                        datatype = XSD.float
                    else:
                        datatype = XSD.string
                    named_graph.add((record_uri, properties[col], Literal(value, datatype=datatype)))  # Ajout du triplet
        return graph_uri

    except Exception as e:
        logger.error(f"Error reading file: {e}")  # Log de l'erreur
        traceback.print_exc()  # Impression de la trace de l'erreur
        return None


# Exécution du module avec python -m SPARQLLM.udf.csv
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG

    # Création d'un graphe RDF sample
    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/SLM-CSV"), slm_csv)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), URIRef("data/results.csv")))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?x  ?z
    WHERE {
        ?s ?p ?value .
        BIND(ex:SLM-CSV(?value) AS ?g)
        graph ?g {
            ?x <http://example.org/city> ?z .
        }
    }
    """

    result = store.query(query_str)  # Exécution de la requête SPARQL
    print_result_as_table(result)  # Affichage des résultats sous forme de tableau