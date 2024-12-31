import unittest  # Importation du module unittest pour les tests unitaires
import socket  # Importation du module socket pour les opérations réseau
import time  # Importation du module time pour les opérations de temporisation
from multiprocessing import Process  # Importation de la classe Process pour la gestion des processus
from flask import Flask, request, jsonify  # Importation des modules Flask pour créer une application web
from rdflib import URIRef, Dataset  # Importation des classes URIRef et Dataset du module rdflib
from SPARQLLM.udf.llmgraph_ollama import LLMGRAPH_OLLAMA  # Importation de la classe LLMGRAPH_OLLAMA du module llmgraph_ollama
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM
from SPARQLLM.config import ConfigSingleton  # Importation de la classe ConfigSingleton du module config
import requests  # Importation du module requests pour les requêtes HTTP

# Flask app pour simuler le serveur OLLAMA
app = Flask(__name__)  # Création de l'application Flask

@app.route('/api/generate', methods=['POST'])  # Définition de la route pour la génération de réponses
def ollama_mock():
    data = request.json  # Récupération des données JSON de la requête
    prompt = data.get('prompt', '')  # Récupération du prompt de la requête

    if 'timeout' in prompt:
        time.sleep(5)  # Simule un délai plus long que le timeout configuré
        return jsonify({"response": "{}"})  # Retourne une réponse JSON vide

    if 'error' in prompt:
        return ('Internal Server Error', 500)  # Retourne une erreur interne du serveur

    if 'invalid' in prompt:
        return jsonify({"response": "{invalid_json}"})  # Retourne une réponse JSON invalide

    return jsonify({
        "response": """
        {
            "@context": "http://schema.org",
            "@type": "Person",
            "name": "John Lennon"
        }
        """
    })  # Retourne une réponse JSON valide

class TestLLMGRAPH_OLLAMA(unittest.TestCase):  # Définition de la classe de test pour la fonction LLMGRAPH_OLLAMA
    @classmethod
    def setUpClass(cls):
        cls.port = cls._find_free_port()  # Trouve un port libre
        cls.api_url = f"http://127.0.0.1:{cls.port}/api/generate"  # Définit l'URL de l'API
        cls.server = Process(target=app.run, kwargs={"port": cls.port, "debug": False, "use_reloader": False})  # Crée un processus pour l'application Flask
        cls.server.start()  # Démarre le serveur
        time.sleep(1)  # Attend que le serveur démarre correctement

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()  # Termine le serveur
        cls.server.join()  # Attend la fin du processus

    @staticmethod
    def _find_free_port():
        """Trouve un port libre sur la machine locale."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Crée un socket
        s.bind(('', 0))  # Lie le socket à un port libre
        port = s.getsockname()[1]  # Récupère le numéro de port
        s.close()  # Ferme le socket
        return port  # Retourne le numéro de port

    def setUp(self):
        global store  # Déclare la variable globale store
        store = Dataset()  # Initialise store avec un nouveau Dataset

        # Injecter l'URL correcte dans la configuration
        config = ConfigSingleton()  # Crée une instance de ConfigSingleton
        config.config['Requests']['SLM-OLLAMA-URL'] = self.api_url  # Définit l'URL de l'API dans la configuration
        config.config['Requests']['SLM-TIMEOUT'] = '2'  # Définit le timeout à 2 secondes pour accélérer les tests

    def test_invalid_uri(self):
        """Test avec un URI invalide."""
        prompt = "Return a JSON-LD schema for a music composition."  # Définit le prompt de test
        uri = "invalid_uri"  # Définit un URI invalide

        graph_uri = LLMGRAPH_OLLAMA(prompt, uri)  # Appel de la fonction LLMGRAPH_OLLAMA avec le prompt et l'URI

        # Vérifiez que l'URI retourné est celui attendu
        self.assertEqual(
            graph_uri,
            URIRef("http://example.org/invalid_uri"),  # Vérifie que l'URI retourné est celui attendu
            "La fonction doit retourner http://example.org/invalid_uri pour un URI invalide."  # Message d'erreur si la vérification échoue
        )

    def test_timeout(self):
        """Test pour simuler un timeout."""
        prompt = "timeout"  # Définit le prompt de test
        uri = URIRef("http://example.org/timeout")  # Définit un URI valide

        with self.assertRaises(requests.exceptions.Timeout):  # Gestion de l'exception de timeout
            LLMGRAPH_OLLAMA(prompt, uri)  # Appel de la fonction LLMGRAPH_OLLAMA avec le prompt et l'URI

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
