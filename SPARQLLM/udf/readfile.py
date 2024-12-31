# Importation des modules nécessaires
from rdflib import Literal, URIRef
from rdflib.namespace import XSD
import html2text
import unidecode
from urllib.parse import urlparse
import logging
from rdflib.plugins.sparql.operators import register_custom_function
from SPARQLLM.udf.SPARQLLM import store

from SPARQLLM.config import ConfigSingleton
from SPARQLLM.utils.utils import print_result_as_table

logger = logging.getLogger(__name__)  # Configuration du logger pour ce module


def readhtmlfile(path_uri, max_size):
    """
    Lit un fichier HTML local et retourne son contenu textuel tronqué à `max_size`.

    Args:
        path_uri (str): URI du fichier à lire.
        max_size (str): Taille maximale du texte retourné.

    Returns:
        Literal: Contenu textuel du fichier ou un message d'erreur.
    """
    max_size = int(max_size)  # Conversion de la taille maximale en entier

    try:
        # Ouverture du fichier en mode lecture
        with open(urlparse(path_uri).path, 'r') as file:
            data = file.read()  # Lecture du contenu du fichier
            h = html2text.HTML2Text()  # Initialisation de l'outil de conversion HTML vers texte
            uri_text = h.handle(data).strip()  # Conversion du HTML en texte et suppression des espaces inutiles
            # Normalisation du texte
            uri_text = uri_text.lstrip("# ").strip()  # Suppression des caractères spéciaux au début
            uri_text_uni = unidecode.unidecode(uri_text).strip()  # Suppression des accents et normalisation
            logger.debug(f"result={uri_text_uni[:max_size]}")  # Log du résultat tronqué
            return Literal(uri_text_uni[:max_size], datatype=XSD.string)  # Retourne le texte tronqué
    except FileNotFoundError:
        logger.error(f"File not found: {path_uri}")  # Log de l'erreur si le fichier n'est pas trouvé
        return Literal(f"Error reading {path_uri}")  # Retourne un message d'erreur
    except OSError as e:
        logger.error(f"OS error: {e}")  # Log de l'erreur système
        return Literal(f"Error reading {path_uri}")  # Retourne un message d'erreur


# Exécution du module avec : python -m SPARQLLM.udf.readfile
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)  # Configuration du logging en mode DEBUG
    config = ConfigSingleton(config_file='config.ini')  # Chargement de la configuration depuis config.ini

    # Enregistrement de la fonction avec un URI personnalisé
    register_custom_function(URIRef("http://example.org/FILE-HTML"), readhtmlfile)

    # Requête SPARQL utilisant la fonction personnalisée
    query_str = """
    PREFIX ex: <http://example.org/>
    SELECT ?uri ?t
    WHERE {
        BIND("data/zenodo.html" AS ?uri)
        BIND(ex:FILE-HTML(?uri,100) AS ?t)
    }
    """

    # Exécution de la requête
    result = store.query(query_str)

    # Affichage des résultats sous forme de tableau
    print_result_as_table(result)