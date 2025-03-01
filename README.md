SPARQLLM proposes a new technique to access external sources during SPARQL query execution.
It allows to easily run SPARQL query that can access Search Engines, Large Language Models, or Vector database. 


# install

```
git clone https://github.com/momo54/SPARQLLM
cd SPARQLLM
pip install .
```

Run a simple queries using the local file system as external source :
```
slm-run --help
slm-run --config config.ini -f queries/simple-csv.sparql --debug
slm-run --config config.ini -f queries/readfile.sparql --debug
slm-run --config config.ini -f queries/ReadDir.sparql --debug
slm-run --config config.ini -f queries/recurse.sparql --debug
```

# Installing synthetic data for Search queries

Create synthetic data and index them:
```
pushd data
python python GenerateEventPages.py
python index.py
popd 
```

Run a simple query with a (local) Search Engine (Whoosh):
```
slm-run --config config.ini -f queries/city-search.sparql --debug
```

If you want to perform the same query on the WEB with Google Search, 
it is not free. If you want to try, your custom search Google API have
to be  activated and  the keys have to be available as environment variables :
```
export SEARCH_API_SOBIKE44=xxxxxxxx_orbIQ302-4NOQhRnxxxxxxx
export SEARCH_CX=x4x3x5x4xfxxxxxxx
```

If well configure, you should be able to run the same query than before with Google
as a search engine.
```
slm-run --config config.google -f queries/city-search.sparql --debug
```

# Calling LLMs

Most LLM are not free to use. If you want to use CHATGPT
your chatGPT api key should be available as an environment variable
```
export OPENAI_API_KEY=xxxxxxxxx
```

We developp with [OLLAMA](https://ollama.com/). You can easily install locally OLLAMA as a server on macOS, Linux, Windows.

If your OLLAMA server is running and models have been installed, then check your config.ini:
```
SLM-OLLAMA-MODEL=llama3.1:latest
SLM-OLLAMA-URL= http://localhost:11434/api/generate
```
We expect OLLAMA server to run on http://localhost:11434/api/generate, and the selected model is llama3.1:latest. If you installed differently, just change accordingly.


SPARQLLM  run:
```
slm-run --config config.ini -f queries/city-search-llm.sparql --debug
```

# Developpers

developping new function is very easy. Just go into SPARQL/udf to see how we wrote User Defined Function you just used, code is very short and can be used as a template for your custom functions. 
