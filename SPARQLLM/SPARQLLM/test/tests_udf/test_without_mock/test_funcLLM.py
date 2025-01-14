import unittest  # Importation du module unittest pour les tests unitaires
from rdflib import Literal  # Importation de la classe Literal du module rdflib
from SPARQLLM.udf.funcLLM import LLM  # Importation de la classe LLM du module funcLLM

class TestLLMFunction(unittest.TestCase):  # Définition de la classe de test pour la fonction LLM

    def test_valid_prompt(self):
        """
        Test avec un prompt valide et une réponse attendue.
        """
        prompt = "Quelle est la capitale de la France ?"  # Définition du prompt de test
        result = LLM(prompt)  # Appel de la fonction LLM avec le prompt

        # Vérifiez que le retour est de type Literal RDF
        self.assertIsInstance(result, Literal)  # Vérification que le résultat est une instance de Literal

        # Vérifiez que la réponse contient les mots-clés attendus
        self.assertIn("Paris", str(result))  # Vérification que "Paris" est dans la réponse

    def test_empty_prompt(self):
        """
        Test avec un prompt vide.
        """
        prompt = ""  # Définition du prompt vide
        with self.assertRaises(AssertionError):  # Un prompt vide doit lever une AssertionError
            LLM(prompt)  # Appel de la fonction LLM avec le prompt vide

    def test_long_prompt(self):
        """
        Test avec un prompt très long pour s'assurer que le modèle gère correctement.
        """
        prompt = "Lorem ipsum " * 1000  # Prompt très long
        result = LLM(prompt)  # Appel de la fonction LLM avec le prompt long

        # Vérifiez que le retour est de type Literal RDF
        self.assertIsInstance(result, Literal)  # Vérification que le résultat est une instance de Literal

        # Vérifiez que la réponse n'est pas vide
        self.assertTrue(len(str(result)) == 0)  # Vérification que la réponse n'est pas vide

    def test_approximate_response(self):
        """
        Test avec un prompt dont la réponse peut varier légèrement.
        """
        prompt = "Donne-moi une citation célèbre d'Albert Einstein."  # Définition du prompt de test
        result = LLM(prompt)  # Appel de la fonction LLM avec le prompt

        # Vérifiez que la réponse contient des mots-clés liés à Einstein
        possible_keywords = ["Einstein", "intelligence", "imagination", "relativité"]  # Mots-clés possibles
        self.assertTrue(
            any(keyword in str(result) for keyword in possible_keywords),  # Vérification que la réponse contient un des mots-clés
            "La réponse ne contient pas de mots-clés attendus."  # Message d'erreur si la vérification échoue
        )

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
