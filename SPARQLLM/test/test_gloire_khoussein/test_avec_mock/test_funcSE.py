# Importation des modules nécessaires
import unittest
from unittest.mock import patch, MagicMock
from rdflib import Literal, URIRef
from SPARQLLM.udf.funcSE import BS4, Google
import requests


class TestFuncSE(unittest.TestCase):
    """
    Classe de tests unitaires pour les fonctions `BS4` et `Google` du module `funcSE`.
    """

    def setUp(self):
        """
        Configuration initiale pour les tests.
        Simule les valeurs de configuration nécessaires pour les fonctions testées.
        """
        self.mock_config = patch('SPARQLLM.udf.funcSE.ConfigSingleton').start()
        self.addCleanup(patch.stopall)  # S'assure que tous les patches sont arrêtés après les tests

        # Simuler les valeurs de configuration
        self.mock_config().config = {
            'Requests': {
                'SLM-TIMEOUT': '10',  # Timeout pour les requêtes HTTP
                'SLM-TRUNCATE': '500',  # Taille maximale du texte tronqué
                'SLM-CUSTOM-SEARCH-URL': 'https://customsearch.googleapis.com/customsearch/v1?cx={se_cx_key}&key={se_api_key}'  # URL de l'API de recherche
            }
        }

    @patch('SPARQLLM.udf.funcSE.requests.get')
    def test_bs4_valid_html(self, mock_get):
        """
        Test de la fonction `BS4` avec une page HTML valide.
        Vérifie que la fonction extrait correctement le texte d'une page HTML.
        """
        mock_response = MagicMock()
        mock_response.headers = {'Content-Type': 'text/html'}  # Simule un contenu HTML
        mock_response.text = "<html><body><p>Hello World!</p></body></html>"  # Contenu HTML simulé
        mock_response.status_code = 200  # Code de statut HTTP réussi
        mock_get.return_value = mock_response  # Simule la réponse de `requests.get`

        uri = "http://example.com"  # URI fictive
        result = BS4(uri)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, Literal)  # Le résultat doit être un Literal RDF
        self.assertEqual(str(result), "Hello World!")  # Le texte extrait doit correspondre
        mock_get.assert_called_once_with(uri, headers={'Accept': 'text/html', 'User-Agent': 'Mozilla/5.0'}, timeout=10)  # Vérifie les paramètres de la requête

    @patch('SPARQLLM.udf.funcSE.requests.get')
    def test_bs4_non_html_content(self, mock_get):
        """
        Test de la fonction `BS4` avec une page qui ne contient pas de HTML.
        Vérifie que la fonction retourne un message approprié pour un contenu non HTML.
        """
        mock_response = MagicMock()
        mock_response.headers = {'Content-Type': 'application/json'}  # Simule un contenu JSON
        mock_response.status_code = 200  # Code de statut HTTP réussi
        mock_get.return_value = mock_response  # Simule la réponse de `requests.get`

        uri = "http://example.com"  # URI fictive
        result = BS4(uri)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, Literal)  # Le résultat doit être un Literal RDF
        self.assertIn("No HTML content at", str(result))  # Le message doit indiquer l'absence de contenu HTML

    @patch('SPARQLLM.udf.funcSE.requests.get')
    def test_bs4_request_error(self, mock_get):
        """
        Test de la fonction `BS4` avec une erreur HTTP.
        Vérifie que la fonction gère correctement les erreurs de requête.
        """
        # Simule une exception levée par `requests.get`
        mock_get.side_effect = requests.exceptions.RequestException("Mocked error")

        uri = "http://example.com"  # URI fictive
        result = BS4(uri)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, Literal)  # Le résultat doit être un Literal RDF
        self.assertIn("Error retreiving", str(result))  # Le message doit indiquer une erreur
        self.assertIn(uri, str(result))  # L'URI problématique doit être mentionné

    @patch('SPARQLLM.udf.funcSE.urlopen')
    @patch('SPARQLLM.udf.funcSE.json.loads')
    def test_google_valid_response(self, mock_json_loads, mock_urlopen):
        """
        Test de la fonction `Google` avec une réponse valide.
        Vérifie que la fonction retourne correctement le premier lien trouvé.
        """
        mock_json_loads.return_value = {
            'items': [{'link': 'http://example.com/result1'}, {'link': 'http://example.com/result2'}]  # Simule des résultats de recherche
        }
        mock_urlopen.return_value.read.return_value.decode.return_value = '{"items": [{"link": "http://example.com/result1"}]}'  # Simule la réponse JSON

        keywords = "test"  # Mots-clés fictifs
        result = Google(keywords)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "http://example.com/result1")  # Le premier lien doit être retourné

    @patch('SPARQLLM.udf.funcSE.urlopen')
    @patch('SPARQLLM.udf.funcSE.json.loads')
    def test_google_no_results(self, mock_json_loads, mock_urlopen):
        """
        Test de la fonction `Google` avec une réponse sans résultats.
        Vérifie que la fonction retourne un URIRef vide en l'absence de résultats.
        """
        mock_json_loads.return_value = {}  # Simule une réponse vide
        mock_urlopen.return_value.read.return_value.decode.return_value = "{}"  # Simule la réponse JSON

        keywords = "test"  # Mots-clés fictifs
        result = Google(keywords)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "")  # Un URIRef vide doit être retourné

    @patch('SPARQLLM.udf.funcSE.urlopen')
    def test_google_request_error(self, mock_urlopen):
        """
        Test de la fonction `Google` avec une erreur HTTP.
        Vérifie que la fonction retourne un URIRef vide en cas d'erreur.
        """
        mock_urlopen.side_effect = Exception("Mocked error")  # Simule une exception

        keywords = "test"  # Mots-clés fictifs
        result = Google(keywords)  # Appel de la fonction à tester

        # Vérifications
        self.assertIsInstance(result, URIRef)  # Le résultat doit être un URIRef
        self.assertEqual(str(result), "")  # Un URIRef vide doit être retourné


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()