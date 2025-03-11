import unittest
from unittest.mock import MagicMock
from rdflib import URIRef
from SPARQLLM.udf.retrieval_se import retrieval_se

class TestRetrievalSE(unittest.TestCase):

    def test_retrieval_se(self):
        # Mock the configuration singleton
        config_mock = MagicMock()
        config_mock.config = {
            'Requests': {
                'SLM-EMBEDDING-MODEL': 'test-model',
                'SLM-FAISS-DBDIR': 'test-db-dir'
            }
        }

        # Mock the named_graph_exists function to return False
        named_graph_exists_mock = MagicMock(return_value=False)

        # Mock the FAISS.load_local function to return a mock vector store
        vector_store_mock = MagicMock()
        vector_store_mock.similarity_search_with_score.return_value = [
            (MagicMock(page_content="Content 1", metadata={'source': 'source1.txt'}), 0.9),
            (MagicMock(page_content="Content 2", metadata={'source': 'source2.txt'}), 0.8)
        ]

        # Mock the store.get_context function to return a mock graph
        graph_mock = MagicMock()

        # Patch the necessary components
        with unittest.mock.patch('SPARQLLM.SPARQLLM.udf.retrieval_se.ConfigSingleton', return_value=config_mock), \
             unittest.mock.patch('SPARQLLM.SPARQLLM.udf.retrieval_se.named_graph_exists', named_graph_exists_mock), \
             unittest.mock.patch('SPARQLLM.SPARQLLM.udf.retrieval_se.FAISS.load_local', return_value=vector_store_mock), \
             unittest.mock.patch('SPARQLLM.SPARQLLM.udf.retrieval_se.store.get_context', return_value=graph_mock):

            # Call the retrieval_se function
            query = "Label: Test Label Objectif: Test Objectif"
            link_to = "http://example.org/test"
            result = retrieval_se(query, link_to, nb_result=2)

            # Check that the result is the expected graph URI
            self.assertEqual(result, URIRef(link_to))

            # Check that the named graph was created with the correct triples
            graph_mock.add.assert_any_call((URIRef(link_to), URIRef("http://example.org/is_aligned_with"), MagicMock()))
            graph_mock.add.assert_any_call((MagicMock(), URIRef("http://example.org/has_ku"), MagicMock()))
            graph_mock.add.assert_any_call((MagicMock(), URIRef("http://example.org/has_source"), URIRef('file://source1.txt')))
            graph_mock.add.assert_any_call((MagicMock(), URIRef("http://example.org/has_score"), MagicMock()))
            graph_mock.add.assert_any_call((MagicMock(), URIRef("http://example.org/has_ka"), MagicMock()))

if __name__ == '__main__':
    unittest.main()