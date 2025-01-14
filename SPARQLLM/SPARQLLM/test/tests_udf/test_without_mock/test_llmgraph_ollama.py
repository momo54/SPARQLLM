import unittest
import socket
import time
from threading import Thread  # Importation pour utiliser des threads au lieu de Process
from flask import Flask, request, jsonify
from rdflib import URIRef, Dataset
from SPARQLLM.udf.llmgraph_ollama import LLMGRAPH_OLLAMA
from SPARQLLM.udf.SPARQLLM import store
from SPARQLLM.config import ConfigSingleton
import requests

"""L'ancienne version marchait sur ubuntu mais pas windows"""
def create_app():
    """Crée une instance de l'application Flask."""
    app = Flask(__name__)

    @app.route('/api/generate', methods=['POST'])
    def ollama_mock():
        data = request.json
        prompt = data.get('prompt', '')

        if 'timeout' in prompt:
            time.sleep(5)
            return jsonify({"response": "{}"})

        if 'error' in prompt:
            return ('Internal Server Error', 500)

        if 'invalid' in prompt:
            return jsonify({"response": "{invalid_json}"})

        return jsonify({
            "response": """
            {
                "@context": "http://schema.org",
                "@type": "Person",
                "name": "John Lennon"
            }
            """
        })

    return app


class TestLLMGRAPH_OLLAMA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = cls._find_free_port()
        cls.api_url = f"http://127.0.0.1:{cls.port}/api/generate"
        cls.app = create_app()
        cls.server_thread = Thread(
            target=cls.app.run,
            kwargs={"port": cls.port, "debug": False, "use_reloader": False}
        )
        cls.server_thread.daemon = True  # Assure que le thread se termine avec le processus principal
        cls.server_thread.start()
        time.sleep(1)  # Laisse le temps au serveur de démarrer

    @classmethod
    def tearDownClass(cls):
        # Le serveur Flask se termine automatiquement avec le thread principal
        pass

    @staticmethod
    def _find_free_port():
        """Trouve un port libre sur la machine locale."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def setUp(self):
        global store
        store = Dataset()
        config = ConfigSingleton()
        config.config['Requests']['SLM-OLLAMA-URL'] = self.api_url
        config.config['Requests']['SLM-TIMEOUT'] = '2'

    def test_invalid_uri(self):
        prompt = "Return a JSON-LD schema for a music composition."
        uri = "invalid_uri"
        graph_uri = LLMGRAPH_OLLAMA(prompt, uri)
        self.assertEqual(
            graph_uri,
            URIRef("http://example.org/invalid_uri"),
            "La fonction doit retourner http://example.org/invalid_uri pour un URI invalide."
        )

    def test_timeout(self):
        prompt = "timeout"
        uri = URIRef("http://example.org/timeout")
        with self.assertRaises(requests.exceptions.Timeout):
            LLMGRAPH_OLLAMA(prompt, uri)


if __name__ == "__main__":
    unittest.main()
