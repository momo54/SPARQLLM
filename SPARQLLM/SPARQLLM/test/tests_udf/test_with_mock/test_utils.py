

import unittest
from rdflib import URIRef, Graph
from unittest.mock import MagicMock, patch
import rdflib
from rdflib import ConjunctiveGraph
import io
from urllib.parse import urlparse
from SPARQLLM.utils.utils import named_graph_exists, print_result_as_table, is_valid_uri, clean_invalid_uris


class TestUtils(unittest.TestCase):
    
    def test_named_graph_exists(self):
        # Créer un ConjunctiveGraph
        conjunctive_graph = ConjunctiveGraph()

        # Ajouter des triples dans des contextes spécifiques
        graph1_uri = URIRef("http://example.com/graph1")
        graph2_uri = URIRef("http://example.com/graph2")
        
        conjunctive_graph.get_context(graph1_uri).add((
            URIRef("http://example.com/subj1"),
            URIRef("http://example.com/pred"),
            URIRef("http://example.com/obj1"),
        ))

        conjunctive_graph.get_context(graph2_uri).add((
            URIRef("http://example.com/subj2"),
            URIRef("http://example.com/pred"),
            URIRef("http://example.com/obj2"),
        ))

        # Vérifier si les named graphs existent
        self.assertTrue(named_graph_exists(conjunctive_graph, graph1_uri))
        self.assertTrue(named_graph_exists(conjunctive_graph, graph2_uri))
        self.assertFalse(named_graph_exists(conjunctive_graph, URIRef("http://example.com/nonexistent_graph")))





    def test_print_result_as_table(self):
        # Mock the results object from rdflib, assuming it has a 'vars' and iterable rows
        mock_results = MagicMock()
        mock_results.vars = ['var1', 'var2']
        mock_results.__iter__.return_value = [
            {'var1': 'value1', 'var2': 'value2'},
            {'var1': 'value3', 'var2': 'value4'}
        ]
        
        # Use patch to redirect stdout to a StringIO object
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            print_result_as_table(mock_results)
            output = fake_out.getvalue()
        
        # Check if the output contains the expected values
        self.assertIn("value1", output)
        self.assertIn("value3", output)
        self.assertIn("value2", output)
        self.assertIn("value4", output)

    def test_is_valid_uri(self):
        # Valid URIs
        self.assertTrue(is_valid_uri("http://example.com"))
        self.assertTrue(is_valid_uri("https://www.test.com/path"))

        # Invalid URIs
        self.assertFalse(is_valid_uri("invalid_uri"))
        self.assertFalse(is_valid_uri("ftp://"))

    def test_clean_invalid_uris(self):
        # Create a graph with valid and invalid URIs
        graph = rdflib.Graph()
        valid_uri = URIRef("http://example.com")
        invalid_uri = URIRef("invalid_uri")

        # Add triples to the graph, including an invalid URI
        graph.add((valid_uri, URIRef("http://example.com/prop"), valid_uri))
        graph.add((invalid_uri, URIRef("http://example.com/prop"), invalid_uri))

        # Call the clean_invalid_uris function
        clean_invalid_uris(graph)

        # Verify that the invalid triple was removed
        self.assertEqual(len(graph), 1)  # Only the valid triple should remain

    def test_is_valid_uri_edge_cases(self):
        # Test edge cases for URI validation
        self.assertFalse(is_valid_uri(""))  # Empty string
        self.assertFalse(is_valid_uri(None))  # None as input
        self.assertFalse(is_valid_uri("http://"))  # Incomplete URI



    def test_clean_invalid_uris_empty_graph(self):
        # Test cleaning an empty graph (no URIs)
        empty_graph = rdflib.Graph()
        clean_invalid_uris(empty_graph)
        self.assertEqual(len(empty_graph), 0)  # Should remain empty

    def test_clean_invalid_uris_no_invalid_uris(self):
        # Test cleaning a graph with only valid URIs
        graph = rdflib.Graph()
        graph.add((URIRef("http://example.com/valid"), URIRef("http://example.com/prop"), URIRef("http://example.com/valid")))
        
        clean_invalid_uris(graph)
        
        # Should remain the same since all URIs are valid
        self.assertEqual(len(graph), 1)


    def test_is_valid_uri_missing_netloc(self):
        # Check URI with missing netloc
        self.assertFalse(is_valid_uri("http:///path"))  # Missing domain name in the URL

if __name__ == '__main__':
    unittest.main()
