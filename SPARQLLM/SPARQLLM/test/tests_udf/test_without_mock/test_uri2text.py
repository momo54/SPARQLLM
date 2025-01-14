import unittest  # Importation du module unittest pour les tests unitaires
from http.server import BaseHTTPRequestHandler, HTTPServer  # Importation des classes pour créer un serveur HTTP
from threading import Thread  # Importation de la classe Thread pour la gestion des threads
from rdflib import Literal, URIRef  # Importation des classes Literal et URIRef du module rdflib
from rdflib.namespace import XSD  # Importation du namespace XSD de rdflib
from SPARQLLM.udf.uri2text import GETTEXT  # Importation de la fonction GETTEXT du module uri2text

# Serveur HTTP pour tester les requêtes GET
class TestHTTPRequestHandler(BaseHTTPRequestHandler):  # Définition de la classe pour gérer les requêtes HTTP
    def do_GET(self):
        if self.path == "/valid":
            # Page HTML valide
            self.send_response(200)  # Envoie une réponse HTTP 200
            self.send_header("Content-Type", "text/html")  # Définit le type de contenu comme HTML
            self.end_headers()  # Termine les en-têtes
            self.wfile.write(b"<html><body><h1>Hello, world!</h1></body></html>")  # Écrit le contenu HTML
        elif self.path == "/non-html":
            # Contenu non HTML
            self.send_response(200)  # Envoie une réponse HTTP 200
            self.send_header("Content-Type", "application/json")  # Définit le type de contenu comme JSON
            self.end_headers()  # Termine les en-têtes
            self.wfile.write(b'{"message": "This is not HTML"}')  # Écrit le contenu JSON
        elif self.path == "/large":
            # Réponse très longue
            self.send_response(200)  # Envoie une réponse HTTP 200
            self.send_header("Content-Type", "text/html")  # Définit le type de contenu comme HTML
            self.end_headers()  # Termine les en-têtes
            self.wfile.write(b"<html><body>" + b"A" * 10000 + b"</body></html>")  # Écrit un contenu HTML très long
        elif self.path == "/timeout":
            # Simulation de timeout
            self.send_response(408)  # Envoie une réponse HTTP 408 (timeout)
            self.end_headers()  # Termine les en-têtes
        elif self.path == "/error":
            # Erreur HTTP 500
            self.send_response(500)  # Envoie une réponse HTTP 500 (erreur interne du serveur)
            self.end_headers()  # Termine les en-têtes
        else:
            self.send_response(404)  # Envoie une réponse HTTP 404 (page non trouvée)
            self.end_headers()  # Termine les en-têtes

class TestGETTEXTFunction(unittest.TestCase):  # Définition de la classe de test pour la fonction GETTEXT
    @classmethod
    def setUpClass(cls):
        """
        Démarre un serveur HTTP local pour les tests.
        """
        cls.server = HTTPServer(("localhost", 8000), TestHTTPRequestHandler)  # Crée un serveur HTTP
        cls.server_thread = Thread(target=cls.server.serve_forever)  # Crée un thread pour le serveur
        cls.server_thread.daemon = True  # Définit le thread comme démon
        cls.server_thread.start()  # Démarre le thread

    @classmethod
    def tearDownClass(cls):
        """
        Arrête le serveur HTTP après les tests.
        """
        cls.server.shutdown()  # Arrête le serveur
        cls.server.server_close()  # Ferme le serveur
        cls.server_thread.join()  # Attend la fin du thread

    def test_valid_html(self):
        """
        Test avec une URI valide retournant du HTML.
        """
        uri = "http://localhost:8000/valid"  # URI de test
        result = GETTEXT(URIRef(uri), 100)  # Appel de la fonction GETTEXT avec l'URI
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(str(result), "Hello, world!")  # Vérifie que le contenu est correct

    def test_non_html_content(self):
        """
        Test avec une URI retournant un type de contenu non HTML.
        """
        uri = "http://localhost:8000/non-html"  # URI de test
        result = GETTEXT(URIRef(uri), 100)  # Appel de la fonction GETTEXT avec l'URI
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(str(result), f"No HTML content at {uri}")  # Vérifie que le contenu est correct

    def test_large_response(self):
        """
        Test avec une réponse très longue tronquée à max_size.
        """
        uri = "http://localhost:8000/large"  # URI de test
        max_size = 500  # Taille maximale
        result = GETTEXT(URIRef(uri), max_size)  # Appel de la fonction GETTEXT avec l'URI et la taille maximale
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(len(str(result)), max_size)  # Vérifie que la longueur du contenu est correcte

    def test_timeout(self):
        """
        Test lorsque le serveur retourne un timeout.
        """
        uri = "http://localhost:8000/timeout"  # URI de test
        result = GETTEXT(URIRef(uri), 100)  # Appel de la fonction GETTEXT avec l'URI
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(str(result), f"Error retrieving {uri}")  # Vérifie que le contenu est correct

    def test_http_error(self):
        """
        Test avec une URI retournant une erreur HTTP.
        """
        uri = "http://localhost:8000/error"  # URI de test
        result = GETTEXT(URIRef(uri), 100)  # Appel de la fonction GETTEXT avec l'URI
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(str(result), f"Error retrieving {uri}")  # Vérifie que le contenu est correct

    def test_invalid_uri(self):
        """
        Test avec une URI invalide.
        """
        uri = "not-a-valid-uri"  # URI invalide
        result = GETTEXT(URIRef(uri), 100)  # Appel de la fonction GETTEXT avec l'URI
        self.assertIsInstance(result, Literal)  # Vérifie que le résultat est une instance de Literal
        self.assertEqual(str(result), f"Error retrieving {uri}")  # Vérifie que le contenu est correct

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
