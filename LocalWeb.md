# Local Search Engine Setup

## Prerequisites

1. **Install Ollama**:
    - Follow the instructions [here](https://ollama.com/download)

2. **Clone the GitHub repository**:
    ```sh
    git clone --branch LocalWeb https://github.com/momo54/SPARQLLM
    cd SPARQLLM
    ```

3. **Set up a virtual environment**:
    ```sh
    python -m venv venv
    ```
    Ou sy python2
   ```sh
   python -m virtualenv venv
   ```

5. **Activate the virtual environment**:
    - On macOS/Linux:
        ```sh
        source venv/bin/activate
        ```
    - On Windows:
        ```sh
        venv\Scripts\activate
        ```

6. **Install the required packages**:
    ```sh
    pip install -U langchain-ollama
    pip install -r requirements.txt
    pip install .
    pip install requests_html
    pip install lxml[html_clean]
    pip install pandas
    pip install git+https://github.com/tasos-py/Search-Engines-Scraper.git
    pip install -U langchain-text-splitters
    pip install langchain_community
    ```

7. **Pull the latest Ollama model**:
    ```sh
    curl https://ollama.ai/install.sh
    ollama pull llama3.1:latest
    ollama pull nomic-embed-text
    ```

## Verify Installation

1. **Check if `slm` is working**:
    ```sh
    slm-run --help
    ```

## Modify Files

**Run the SPARQL query**:
    ```sh
    slm-run --config config.ini -f queries/wikidata_mekano.sparql --debug
    ```

## Troubleshooting

1. **If you encounter an SSL error**:
    - Modify `http_client.py`:
        - File: `venv/Lib/site-packages/search_engines/http_client.py`
        - Change line 23:
            ```python
            req = self.session.post(page, data, timeout=self.timeout)
            ```
          To:
            ```python
            req = self.session.get(page, timeout=self.timeout, verify=False)
            ```
        - Change line 33:
            ```python
            req = self.session.post(page, data, timeout=self.timeout, verify=False)
            ```

## Run Folder Search Functions

1. **Run `folder_search_content`**:
    ```sh
    python -m SPARQLLM.udf.folder_search_content
    ```

2. **Run `folder_search_paths`**:
    ```sh
    python -m SPARQLLM.udf.folder_search_paths
    ```

## Run Wikidata Local SE Query

1. **Run the `wikidata_local_se.sparql` query**:
    ```sh
    slm-run --config config.ini -f queries/wikidata_local_se.sparql --debug
    ```
