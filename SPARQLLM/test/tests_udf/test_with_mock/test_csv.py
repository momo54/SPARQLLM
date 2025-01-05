# Importation des modules nécessaires
import unittest
from unittest.mock import patch, mock_open
from rdflib import URIRef, Literal
from rdflib.namespace import XSD
from SPARQLLM.udf.csv import slm_csv
from SPARQLLM.udf.SPARQLLM import store
import pandas as pd


class TestSLMCSVFunction(unittest.TestCase):
    """
    Classe de tests unitaires pour la fonction `slm_csv` qui convertit un fichier CSV en graphe RDF.
    """

    def setUp(self):
        """
        Préparation avant chaque test : nettoyage du store RDF.
        """
        store.remove((None, None, None))  # Suppression de tous les triplets du store RDF

    def test_valid_csv(self):
        """
        Test avec un fichier CSV valide.
        Vérifie que la fonction `slm_csv` génère correctement un graphe RDF à partir d'un fichier CSV valide.
        """
        csv_content = """date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
1872-11-30,Scotland,England,0,0,Friendly,Glasgow,Scotland,FALSE
1873-03-08,England,Scotland,4,2,Friendly,London,England,FALSE"""  # Contenu CSV simulé
        file_url = "file:///tmp/test.csv"  # URL fictive du fichier CSV

        # Simulation de l'ouverture du fichier et de la lecture du CSV
        with patch("builtins.open", mock_open(read_data=csv_content)), \
             patch("pandas.read_csv", return_value=pd.read_csv("/tmp/test.csv")):
            graph_uri = slm_csv(file_url)  # Appel de la fonction à tester

        # Vérification que le graphe RDF est correctement créé
        self.assertIsNotNone(graph_uri, "Le graphe RDF ne doit pas être None pour un fichier CSV valide.")
        named_graph = store.get_context(graph_uri)
        self.assertGreater(len(named_graph), 0, "Le graphe RDF doit contenir des triplets.")

        # Vérification précise des triplets générés
        expected_triples_count = 20  # Nombre de triplets attendus basé sur les lignes du CSV simulé
        self.assertEqual(len(named_graph), expected_triples_count,
                         f"Le graphe RDF doit contenir {expected_triples_count} triplets pour ces données.")

    def test_csv_with_mixed_data_types(self):
        """
        Test avec un fichier CSV contenant des colonnes de types de données mélangés.
        Vérifie que la fonction `slm_csv` gère correctement les types de données (entiers, flottants, chaînes).
        """
        csv_content = """name,age,salary,is_manager
John,30,50000.5,TRUE
Alice,25,45000,FALSE
Bob,40,60000.75,FALSE"""  # Contenu CSV simulé avec des types de données mélangés
        file_url = "file:///tmp/mixed_types.csv"  # URL fictive du fichier CSV

        # Simulation de l'ouverture du fichier et de la lecture du CSV
        with patch("builtins.open", mock_open(read_data=csv_content)), \
             patch("pandas.read_csv", return_value=pd.read_csv("/tmp/mixed_types.csv")):
            graph_uri = slm_csv(file_url)  # Appel de la fonction à tester

        # Vérification que le graphe RDF est correctement créé
        self.assertIsNotNone(graph_uri, "Le graphe RDF ne doit pas être None pour un fichier CSV valide.")
        named_graph = store.get_context(graph_uri)

        # Vérification que les types de données sont correctement attribués
        for triple in named_graph:
            _, _, o = triple
            if isinstance(o, Literal):
                if o.datatype == XSD.integer:
                    self.assertTrue(isinstance(o.toPython(), int), "Le type devrait être un entier.")
                elif o.datatype == XSD.float:
                    self.assertTrue(isinstance(o.toPython(), float), "Le type devrait être un flottant.")
                elif o.datatype == XSD.string:
                    self.assertTrue(isinstance(o.toPython(), str), "Le type devrait être une chaîne.")

    def test_csv_with_malformed_data(self):
        """
        Test avec un fichier CSV contenant des données mal formées.
        Vérifie que la fonction `slm_csv` ne crée pas de graphe RDF pour un fichier CSV mal formé.
        """
        csv_content = """date,home_team,away_team,home_score,away_score
1872-11-30,Scotland,England,0,
1873-03-08,England,Scotland,4,2,Friendly"""  # Contenu CSV simulé avec des données mal formées
        file_url = "file:///tmp/malformed.csv"  # URL fictive du fichier CSV

        # Simulation de l'ouverture du fichier et de la lecture du CSV avec une erreur de parsing
        with patch("builtins.open", mock_open(read_data=csv_content)), \
             patch("pandas.read_csv", side_effect=pd.errors.ParserError("Erreur de parsing")):
            graph_uri = slm_csv(file_url)  # Appel de la fonction à tester

        # Vérification qu'aucun graphe RDF n'est créé pour des données mal formées
        self.assertIsNone(graph_uri, "Aucun graphe ne doit être créé pour un fichier CSV mal formé.")


# Exécution des tests unitaires
if __name__ == "__main__":
    unittest.main()