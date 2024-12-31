import unittest  # Importation du module unittest pour les tests unitaires
from rdflib import URIRef, Dataset, Literal, logger  # Importation des classes et fonctions nécessaires de rdflib
from rdflib.namespace import RDF, FOAF  # Importation des namespaces RDF et FOAF de rdflib
from SPARQLLM.udf.llmgraph import LLMGRAPH  # Importation de la classe LLMGRAPH du module llmgraph
from SPARQLLM.udf.SPARQLLM import store  # Importation de la variable store du module SPARQLLM

class TestLLMGRAPH(unittest.TestCase):  # Définition de la classe de test pour la fonction LLMGRAPH
    def setUp(self):
        global store  # Déclare la variable globale store
        store = Dataset()  # Initialise store avec un nouveau Dataset

        # Réponses simulées pour différents cas au format Turtle
        self.valid_person_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person> a schema:Person ;
            schema:name "John Doe" ;
            schema:givenName "John" ;
            schema:familyName "Doe" .
        """  # Turtle valide pour une personne

        self.malformed_turtle = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person a schema:Person .
        """  # Mauvais format Turtle

        self.empty_turtle = ""  # Simule une réponse vide (timeout ou absence de contenu)

    def test_valid_person_rdf_parsing(self):
        """Vérifie directement que le contenu Turtle est valide."""
        rdf_graph = Dataset()  # Crée un nouveau Dataset
        rdf_data = """
        @prefix schema: <https://schema.org/> .
        <http://example.org/person> a schema:Person ;
            schema:name "John Doe" ;
            schema:givenName "John" ;
            schema:familyName "Doe" .
        """  # Données Turtle valides
        try:
            rdf_graph.parse(data=rdf_data, format="turtle")  # Parse les données Turtle
            logger.debug("Le contenu Turtle a été chargé avec succès.")  # Log de succès

            # Vérification des triplets
            uri = URIRef("http://example.org/person")  # URI de la personne
            types = list(rdf_graph.objects(subject=uri, predicate=RDF.type))  # Récupère les types de l'URI
            self.assertIn(URIRef("https://schema.org/Person"), types)  # Vérifie que l'URI est de type Person

        except Exception as e:
            self.fail(f"Le parsing du contenu Turtle a échoué : {e}")  # Échec du parsing

    def test_invalid_uri(self):
        """Test avec un URI invalide."""
        prompt = "Return a Turtle RDF schema for a music composition."  # Définit le prompt de test
        uri = "invalid_uri"  # URI invalide

        with self.assertRaises(ValueError):  # Gestion de l'exception ValueError
            LLMGRAPH(prompt, uri, response_override=self.valid_person_turtle)  # Appel de la fonction LLMGRAPH avec le prompt et l'URI

    def test_malformed_turtle_response(self):
        """Test avec une réponse RDF Turtle malformée."""
        uri = URIRef("http://example.org/malformed_turtle")  # URI valide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            LLMGRAPH("Malformed Turtle RDF test", uri, response_override=self.malformed_turtle)  # Appel de la fonction LLMGRAPH avec le prompt et l'URI
        self.assertIn("Parse Error", str(context.exception))  # Vérifie que l'exception contient "Parse Error"

    def test_empty_response(self):
        """Test avec une réponse RDF Turtle vide."""
        uri = URIRef("http://example.org/empty_response")  # URI valide

        with self.assertRaises(ValueError) as context:  # Gestion de l'exception ValueError
            LLMGRAPH("Empty Turtle RDF test", uri, response_override=self.empty_turtle)  # Appel de la fonction LLMGRAPH avec le prompt et l'URI
        self.assertIn("Parse Error", str(context.exception))  # Vérifie que l'exception contient "Parse Error"

if __name__ == "__main__":
    unittest.main()  # Exécution des tests si le script est exécuté directement
