## Overview

This repository provides  an implementation of Graph Generating Functions (GGFs) for SPARQL. GGFs provide a simple way to enable Retreival Augmentation (RAG) for SPARQL. Thanks to GGF, it is possible to call a search engine, a LLM, a vector database during SPARQL query execution. A simple example of neuro-symbolic processing is:

```
# slm-run --config config.ini -f queries/LLM/hello_neuro.sparql --debug

PREFIX ggf: <http://ggf.org/>
PREFIX schema: <https://schema.org/>

SELECT ?msg {
    BIND("""Say Hello to the neuro-symbolic world:
    Return *ONLY* a JSON-LD object of type `Event` in the following format:
    {
      "@context": "https://schema.org/",
      "@type": "Event",
      "message": "text",
    }
    """ AS ?prompt)
    BIND(ggf:LLM(?prompt) AS ?g)
     GRAPH ?g {
        ?root a schema:Event. 
        OPTIONAL { ?root schema:message ?msg . }
     }
}
```


This README focuses on running a first query without any API key or remote dependency. Optional advanced capabilities (web search, online LLMs, vector similarity) can be enabled later but are not required for the basic examples below. 

## Exploring Example Queries

Many example queries are available in the [`queries/`](https://github.com/GDD-Nantes/SPARQLLM/tree/recurse/queries) directory covering various use cases:

- **`filesystem/`** – File reading, directory iteration
- **`LLM/`** – Direct LLM prompting and neuro-symbolic processing
- **`entitysearch/`** – Entity linking, Wikidata integration, CBD extraction, summarization
- **`web/`** – Web search (DuckDuckGo), entity reranking, web snapshots
- **`faiss/`** – Vector similarity search with FAISS
- **`experimental/`** – Prototype and experimental queries

Browse the `queries/` folder on GitHub to discover more patterns and inspiration for your own queries.


## running 
```
% slm-run --help
Usage: slm-run [OPTIONS]

Options:
  -q, --query TEXT          SPARQL query to execute (passed in command-line)
  -f, --file TEXT           File containing a SPARQL query to execute
  -c, --config TEXT         Config File for User Defined Functions
  -l, --load TEXT           RDF data file to load
  -fo, --format TEXT        Format of RDF data file
  -d, --debug               turn on debug.
  -k, --keep-store TEXT     File to store the RDF data collected during the
                            query
  -o, --output-result TEXT  File to store the result of the query.
  -o, --output-result TEXT  File to store the result in CSV of the query.
  --help                    Show this message and exit.
```

## Key Features (short list)
* Extend SPARQL with Graph Generating Functions (GGFs) returning fresh RDF graphs.
* Allows to call any external API during SPARQL query processing including LLM, Vector database, SQL etc...

## Quick Start (offline only)

Clone and install (Python 3.10+ recommended):
```
git clone <your-fork-or-clone-url>
cd SPARQLLM
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install .
```

Verify the command‑line tool is available:
```
slm-run --help
```

## Minimal Configuration

The file `config.ini` already contains default sections. No API keys are needed for local file queries. You can proceed directly to execution.

## First Example: Read a Local CSV

Run a SPARQL query that loads and inspects a small CSV file (see `queries/simple-csv.sparql`):
```
slm-run --config config.ini -f queries/filesystem/simple-csv.sparql --debug
```
Use `--debug` to see which custom functions are registered and how graphs are materialized.

### Read a Single File
```
slm-run --config config.ini -f queries/filesystem/readfile.sparql --debug
```

### Iterate Over a Directory
```
slm-run --config config.ini -f queries/ReadDir.sparql --debug
```

These examples prove the local GGFs (file and directory access) are working with no external services.


## Inspecting Results
By default, query solutions stream to stdout. To persist the result bindings (one row per line) use:
```
slm-run --config config.ini -f queries/readfile.sparql -o result.txt
```

To keep all intermediate named graphs for later offline replay:
```
slm-run --config config.ini -f queries/readfile.sparql --keep-store session.nq
```
Then rerun the logic (adding new clauses or different projection) without touching the network:
```
slm-run --config config.ini --load session.nq --format nquads -q "SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }"
```

## Optional: Local Search / Vector (No API Keys)
If you want local text search or approximate vector similarity you can build indices. These steps are optional and can be skipped for a first run.

1. Build a Whoosh index (keyword search):
```
slm-index-whoosh
```
2. Build a FAISS index (vector embeddings):
```
slm-index-faiss
```
3. Test:
```
slm-search-whoosh --help
slm-search-faiss --help
```

Queries that combine Wikidata (remote public SPARQL endpoint) with local search exist under `queries/` (e.g., `city-search.sparql`). These do not require private API keys but do rely on the public Wikidata endpoint being reachable.

## Optional: Local LLM via Ollama (No API Key)
If you have [Ollama](https://ollama.com/) installed you can enable local LLM generation without any API key:
```
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.1:latest
```
Then adapt a query calling the local LLM function variants (see queries containing `LLMGRAPH_OLLA`). This is entirely optional.

## Advanced (Requires External Keys – Omitted by Default)
The codebase also supports web search APIs and hosted LLM providers (e.g., OpenAI, Groq, Mistral). These require setting environment variables and adjusting `[Requests]` in `config.ini`. Since the goal here is a key‑less onboarding path, detailed instructions are intentionally omitted. You can discover the expected variable names by searching for provider modules in `SPARQLLM/udf/`.

## Running With Debug Logs
Use `--debug` to activate verbose logging (registration of custom functions, external call timing, provenance enrichment). This is helpful when authoring new queries or diagnosing performance.

## Keeping Things Deterministic
For reproducibility across environments:
* Pin dependencies in `requirements.txt` (already present).
* Use `--keep-store` to freeze retrieved graphs.
* Rerun with `--load` to avoid external calls.

## Query Authoring Patterns
Custom functions typically bind a named graph that you immediately re‑enter:
```
BIND(ex:SLM-READFILE(?path) AS ?g)
GRAPH ?g { ?doc ?p ?o }
```
This pattern lets you chain multiple stages (e.g., directory listing → file read → lightweight extraction) inside one SPARQL query.

Some aliases may hide verbose JSON argument objects. When available they appear as simple function calls (e.g., `ggf:SEARCH("term")`). Inspect existing queries for concrete usage.

## Testing
Run the test suite (fast, mostly local):
```
pytest -q
```

## Troubleshooting
| Symptom | Likely Cause | Quick Fix |
| ------- | ------------ | --------- |
| Command `slm-run` not found | Package not installed in current venv | Re‑activate venv, `pip install .` |
| Empty query results | Projection variables not bound | Add a temporary `SELECT *` to inspect bindings |
| Slow run | Remote endpoint (e.g., Wikidata) latency | Test with a local file query first |
| Function URI collision | Duplicate alias registration | Adjust alias name or guard registration |

## Contributing (Neutral Guidelines)
1. Keep new UDFs minimal; return a coherent named graph.
2. Add a focused test where practical.
3. Avoid introducing hard API key dependencies in core logic.
4. Prefer pure Python standard library unless a dependency adds clear value.

## License
Refer to the repository’s license file (if present) for usage terms. In absence of an explicit license, treat the code as “all rights reserved” until clarified.

---
You now have everything needed to execute a first SPARQL query locally with no API keys. Explore `queries/` and iterate from there.