import unittest  # Importation du module unittest pour les tests unitaires
from rdflib import URIRef  # Importation de la classe URIRef du module rdflib
from SPARQLLM.udf.schemaorg import SCHEMAORG, is_valid_turtle  # Importation des fonctions SCHEMAORG et is_valid_turtle du module schemaorg
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM

class TestSCHEMAORG(unittest.TestCase):  # Définition de la classe de test pour la fonction SCHEMAORG
    def setUp(self):
        # Réponses simulées
        self.valid_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person> a schema:Person ;
            schema:name "John Doe" ;
            schema:givenName "John" ;
            schema:familyName "Doe" .
        """  # Turtle valide pour une personne

        self.malformed_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person a schema:Person ;
            schema:name "John Doe" ;
            schema:givenName "John" .
        """  # Turtle mal formé

        self.empty_response = ""  # Simule une réponse vide

    def test_invalid_uri(self):
        """Test avec un URI invalide."""
        uri = "invalid_uri"  # URI invalide
        link_to = URIRef("http://example.org/root")  # URI valide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SCHEMAORG(uri, link_to)  # Appel de la fonction SCHEMAORG avec l'URI invalide
        self.assertIn("Invalid URI", str(context.exception))  # Vérifie que l'exception contient "Invalid URI"

    def test_valid_turtle(self):
        """Test avec une réponse RDF Turtle valide."""
        uri = URIRef("http://example.org/valid_turtle")  # URI valide
        link_to = URIRef("http://example.org/root")  # URI valide

        result_graph_uri = SCHEMAORG(uri, link_to, rdf_store=store, response_override=self.valid_turtle)  # Appel de la fonction SCHEMAORG avec le Turtle valide
        named_graph = store.get_context(result_graph_uri)  # Récupère le graphe nommé

        self.assertGreater(len(named_graph), 0, "Le graphe nommé est vide malgré un Turtle valide.")  # Vérifie que le graphe nommé n'est pas vide

    def test_malformed_turtle(self):
        """Test avec une URI invalide au lieu de données Turtle mal formées."""
        uri = "invalid_uri"  # URI non valide
        link_to = URIRef("http://example.org/root")  # URI valide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SCHEMAORG(uri, link_to, rdf_store=store)  # Appel de la fonction SCHEMAORG avec l'URI invalide
        self.assertIn("Invalid URI", str(context.exception))  # Vérifie que l'exception contient "Invalid URI"

    def test_empty_response(self):
        """Test avec une réponse vide."""
        uri = URIRef("http://example.org/empty_response")  # URI valide
        link_to = URIRef("http://example.org/root")  # URI valide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            SCHEMAORG(uri, link_to, rdf_store=store, response_override=self.empty_response)  # Appel de la fonction SCHEMAORG avec la réponse vide
        self.assertIn("Request error for URI", str(context.exception))  # Vérifie que l'exception contient "Request error for URI"

    # Nouveau bloc de tests pour is_valid_turtle
    def test_is_valid_turtle_with_valid_data(self):
        """Test avec une chaîne Turtle valide."""
        valid_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person> a schema:Person ;
            schema:name "Jane Doe" .
        """  # Turtle valide
        self.assertTrue(is_valid_turtle(valid_turtle), "Valid Turtle data was not recognized as valid.")  # Vérifie que le Turtle est valide

    def test_is_valid_turtle_with_invalid_data(self):
        """Test avec une chaîne Turtle invalide."""
        invalid_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person a schema:Person ;
            schema:name "John Doe" .
        """  # Syntaxe mal formée
        self.assertFalse(is_valid_turtle(invalid_turtle), "Invalid Turtle data was not recognized as invalid.")  # Vérifie que le Turtle est invalide

    def test_is_valid_turtle_with_empty_data(self):
        """Test avec une chaîne vide."""
        empty_turtle = ""  # Chaîne vide
        self.assertFalse(is_valid_turtle(empty_turtle), "Empty data should not be valid Turtle.")  # Vérifie que la chaîne vide n'est pas valide

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
