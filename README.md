SPARQLLM proposes a new technique to access external sources during SPARQL query execution.
It allows to easily run SPARQL query that can access Search Engines, Large Language Models, or Vector database. You can easily try with

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/momo54/SPARQLLM?quickstart=1)



# install

```
git clone https://github.com/momo54/SPARQLLM
cd SPARQLLM
```



install with virtualenv (recommended):
```
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
pip install .
```

You should be able to run: `slm-run --help`
```
Usage: slm-run [OPTIONS]

Options:
  -q, --query TEXT          SPARQL query to execute (passed in command-line)
  -f, --file TEXT           File containing a SPARQL query to execute
  -c, --config TEXT         Config File for User Defined Functions
  -l, --load TEXT           RDF data file to load
  -fo, --format TEXT        Format of RDF data file
  -d, --debug               turn on debug.
  -k, --keep-store TEXT     File to store the RDF data collected during the
  -o, --output-result TEXT  File to store the result of the query query. 1
                            line per result
  --help                    Show this message and exit.
```

# Run queries working with the local file system


Run a simple queries using the local file system as external source :
```
slm-run --config config.ini -f queries/simple-csv.sparql --debug
slm-run --config config.ini -f queries/readfile.sparql --debug
slm-run --config config.ini -f queries/ReadDir.sparql --debug
```

We can read files, html-files, csv-files, directories during query processing.


# Install Search, Vector and LLM capabilities

Need Ollama installed, For Linux, MacOS:
```
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.1:latest
ollama pull nomic-embed-text
```

Need index and semantic index:
```
cd data
python index_whoosh.py
python index_faiss.py
cd ..
```

Run a simple query with a (local) Search Engine [Whoosh](https://github.com/whoosh-community/whoosh):
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```

Combine Wikidata, Vector Search and LLM in a single query [See the query](queries/city-search-faiss-llm.sparql)
```
slm-run --config config.ini -f queries/city-search-faiss-llm.sparql --debug
```

Same query with keyword search instead of vector search:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```


## Working with web search engines

If you want to perform the same query on the WEB with [Google Search API](https://developers.google.com/custom-search), your custom search Google API have
to be  activated and the keys have to be available as environment variables :
```
export GOOGLE_API_KEY=xxxxxxxx_orbIQ302-4NOQhRnxxxxxxx
export GOOGLE_CX=x4x3x5x4xfxxxxxxx
```

You should be able to run the same query than before with Google
as a search engine.
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```


## Working a online LLMs

If you  use MISTRAL AI, your MistralAI API key should be available as an environment variable:
```
export MISTRAL_API_KEY='xxxx'
```

Model to use should be configured in config.ini:
```
...
[Requests]
...
SLM-MISTRALAI-MODEL=ministral-8b-latest
```

test the same query with:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```


If you want to use CHATGPT, your chatGPT api key should be available as an environment variable
```
export OPENAI_API_KEY=xxxxxxxxx
```

Model to use should be configured in config.ini:
```
...
[Requests]
...
SLM-OPENAI-MODEL=gpt-3.5-turbo-0125
```

test the same query with:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```


# Developpers

Developping new function is very easy. Just go into SPARQL/udf to see how we wrote User Defined Functions you just used, code is very short and can be used as a template for your custom functions. 

You can run tests by  just typing :
```
pytest
```