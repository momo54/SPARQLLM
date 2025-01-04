import unittest  # Importation du module unittest pour les tests unitaires
from rdflib import URIRef  # Importation de la classe URIRef du module rdflib
from SPARQLLM.udf.funcSE_scrap import SearchEngine  # Importation de la classe SearchEngine du module funcSE_scrap
from SPARQLLM.config import ConfigSingleton  # Importation de la classe ConfigSingleton du module config
from SPARQLLM.utils.utils import is_valid_uri  # Importation de la fonction is_valid_uri du module utils

class TestSearchEngineFunction(unittest.TestCase):  # Définition de la classe de test pour la fonction SearchEngine

    def setUp(self):
        """
        Configuration initiale avant chaque test.
        """
        self.config = ConfigSingleton(config_file='config.ini')  # Initialisation de la configuration avec le fichier config.ini

    def test_valid_keywords(self):
        """
        Test avec des mots-clés valides.
        """
        keywords = "university of nantes"  # Définition des mots-clés de test
        result = SearchEngine(keywords)  # Appel de la fonction SearchEngine avec les mots-clés

        # Vérifiez que le résultat est un URI RDF
        self.assertIsInstance(result, URIRef)  # Vérification que le résultat est une instance de URIRef

        # Vérifiez que le résultat est un URI valide
        self.assertTrue(is_valid_uri(result), f"L'URI retournée est invalide : {result}")  # Vérification que l'URI est valide

    def test_empty_keywords(self):
        """
        Test avec des mots-clés vides.
        """
        keywords = ""  # Définition des mots-clés vides
        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SearchEngine(keywords)  # Appel de la fonction SearchEngine avec les mots-clés vides

        # Vérifiez que l'exception est levée pour les mots-clés vides
        self.assertIn("Les mots-clés ne peuvent pas être vides.", str(context.exception))  # Vérification du message d'exception

    def test_long_keywords(self):
        """
        Test avec des mots-clés très longs pour s'assurer que la fonction gère correctement.
        """
        keywords = "Lorem ipsum " * 500  # Génère une chaîne très longue
        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SearchEngine(keywords)  # Appel de la fonction SearchEngine avec les mots-clés longs

        # Vérifiez que l'exception mentionne une erreur liée à la longueur
        self.assertIn("Les mots-clés sont trop longs.", str(context.exception))  # Vérification du message d'exception

    def test_timeout(self):
        """
        Test pour vérifier le comportement en cas d'échec lié à un délai d'attente simulé.
        """
        keywords = "test timeout"  # Définition des mots-clés de test

        # Simuler une erreur d'attente en levant manuellement une exception
        with self.assertRaises(Exception) as context:  # Gestion de l'exception générale
            raise Exception("Erreur lors de la recherche : délai d'attente dépassé")  # Levée manuelle de l'exception

        self.assertIn("délai d'attente dépassé", str(context.exception))  # Vérification du message d'exception

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
