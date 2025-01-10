# Importation des modules nécessaires
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.operators import register_custom_function

from string import Template

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table
from SPARQLLM.udf.SPARQLLM import store

import logging
logger = logging.getLogger(__name__)  # Configuration du logger pour ce module

from openai import OpenAI, BadRequestError
import os

# Initialisation du client OpenAI
client = OpenAI(
    # La clé API est récupérée depuis les variables d'environnement
    api_key=os.environ.get("OPENAI_API_KEY"),
)


def LLM(prompt):
    """
    Fonction pour interagir avec un modèle de langage (LLM) via l'API OpenAI.

    Args:
        prompt (str): Le texte d'entrée (prompt) à envoyer au modèle.

    Returns:
        Literal: Le texte généré par le modèle, encapsulé dans un objet Literal RDF.

    Raises:
        AssertionError: Si le modèle OpenAI n'est pas configuré ou si le prompt est vide.
    """
    config = ConfigSingleton()  # Récupération de la configuration singleton
    model = config.config['Requests']['SLM-OPENAI-MODEL']  # Récupération du modèle OpenAI depuis la configuration
    assert model != "", "OpenAI Model not set in config.ini"  # Vérification que le modèle est configuré

    # Vérification pour un prompt vide
    assert prompt.strip() != "", "Le prompt ne peut pas être vide."

    logger.debug(f"prompt: {prompt}, model: {model}")  # Log du prompt et du modèle utilisé

    try:
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


        # Extraction du texte généré depuis la réponse
        generated_text = response.choices[0].message.content

    except BadRequestError:
        generated_text = ""
    
    return Literal(generated_text)  # Retourne le texte généré encapsulé dans un objet Literal RDF


# Exécution du module avec : python -m SPARQLLM.udf.funcLLM
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/LLM"), LLM)

    # Ajout de données sample au graphe
    store.add((URIRef("http://example.org/subject1"), URIRef("http://example.org/hasValue"), Literal(5, datatype=XSD.integer)))

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?result
    WHERE {
        ?s ?p ?value .
        BIND(ex:LLM(REPLACE("NOMBRE est plus grand que ?","NOMBRE",STR(?value))) AS ?result)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)