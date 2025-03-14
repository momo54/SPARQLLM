import pytest
import subprocess
import os

# Dossier contenant les fichiers SPARQL
SPARQL_QUERY_DIR = "queries/"

# Liste des tests : (fichier requête, arguments spécifiques à `slm-run`, nombre attendu de résultats)
TEST_QUERIES = [
    ("simple-csv.sparql", "--config config.ini -o /tmp/out.txt -f ", 47778),
    ("readfile.sparql", "--config config.ini -o /tmp/out.txt -f ", 8),
    ("ReadDir.sparql", "--config config.ini -o /tmp/out.txt -f ", 5),
    ("directory_recurse.sparql", "--config config.ini -o /tmp/out.txt -f ", 2),
]

# Liste des tests : (fichier requête, arguments spécifiques à `slm-run`, nombre attendu de résultats)
TEST_QUERIES_SE_LLM = [
    ("city-search-llm.sparql", "--config config.ini -o /tmp/out.txt -f ", 1),
]

import requests
import pytest

def ollama_is_running():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def required_directories_exist():
    """Vérifie si les répertoires nécessaires existent."""
    return os.path.isdir("data/events") and os.path.isdir("data/whoosh_store") and os.path.isdir("data/faiss_store")


@pytest.mark.skipif(not (ollama_is_running() and required_directories_exist()), reason="Ollama server is not running or data/index no present")
@pytest.mark.parametrize("query_file, cli_options, expected_count", TEST_QUERIES)
def test_sparql_queries(query_file, cli_options, expected_count):
    """Exécute une requête SPARQL avec `slm-run` et vérifie le nombre de résultats."""
    query_path = os.path.join(SPARQL_QUERY_DIR, query_file)

    try:
        # Construire la commande `slm-run`
        command = f"slm-run {cli_options} {query_path}"

        # Exécuter la commande et récupérer la sortie
        subprocess.run(command, shell=True, check=True)

        # Compter le nombre de lignes dans le fichier de sortie
        with open("/tmp/out.txt", "r") as f:
            result_count = sum(1 for _ in f)

        # Vérifier le nombre de résultats
        assert result_count == expected_count, f"Expected {expected_count} results, got {result_count}"
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Query execution failed: {e}")


@pytest.mark.parametrize("query_file, cli_options, expected_count", TEST_QUERIES_SE_LLM)
def test_sparql_queries_se_llm(query_file, cli_options, expected_count):
    """Exécute une requête SPARQL avec `slm-run` et vérifie le nombre de résultats."""
    query_path = os.path.join(SPARQL_QUERY_DIR, query_file)

    try:
        # Construire la commande `slm-run`
        command = f"slm-run {cli_options} {query_path}"

        # Exécuter la commande et récupérer la sortie
        subprocess.run(command, shell=True, check=True)

        # Compter le nombre de lignes dans le fichier de sortie
        with open("/tmp/out.txt", "r") as f:
            result_count = sum(1 for _ in f)

        # Vérifier le nombre de résultats
        # with LLM -> the number of results is not deterministic
        assert result_count >= expected_count, f"Expected {expected_count} results, got {result_count}"
    except subprocess.CalledProcessError as e:
        pytest.fail(f"Query execution failed: {e}")

