# SPARQLLM

This repository contains experimental code for running graph-oriented functions
inside SPARQL. Its main focus is Graph Generating Functions (GGFs): custom
SPARQL functions that materialize intermediate named graphs, which can then be
queried or passed to other functions in the same SPARQL query.

The repository also includes Python scripts used as baselines, evaluation
runners, plotting helpers, and experiment tooling. These scripts often reproduce
the same operations through explicit client-side orchestration, making it
possible to compare execution time, logical call counts, and transferred data
volume between GGF and script-based workflows.

## GGF Pattern

Functions declared in [`config.ini`](config.ini) are registered under the
`http://ggf.org/` namespace. A typical GGF query follows this pattern:

```sparql
PREFIX ggf: <http://ggf.org/>

SELECT ?s ?p ?o
WHERE {
  BIND(ggf:EXPAND(<http://metaqa.org/entity/taxidermia>, 1, "both") AS ?g)

  GRAPH ?g {
    ?s ?p ?o .
  }
}
```

The function returns the IRI of a named graph. The generated triples remain in
the RDF store and can be queried immediately or used as input to another GGF.

## Repository Layout

- [`SPARQLLM/`](SPARQLLM/): Python package, CLI, and UDF/GGF implementations.
- [`SPARQLLM/udf/`](SPARQLLM/udf/): custom SPARQL functions.
- [`queries/`](queries/): example SPARQL queries grouped by domain.
- [`queries/bench/`](queries/bench/): isolated GGF examples and benchmark queries.
- [`xp-ggf-script/`](xp-ggf-script/): main workspace for GGF vs script comparisons on MetaQA.
- [`scripts/`](scripts/): Python evaluation, conversion, plotting, and baseline scripts.
- [`data/`](data/): local datasets and indexes used by examples.
- [`tests/`](tests/): project tests.

## Installation

The package declares Python `>=3.12` in [`setup.py`](setup.py).

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Check that the main command is available:

```bash
slm-run --help
```

The CLI can also be invoked as a Python module:

```bash
python -m SPARQLLM.cli.slm --help
```

## SPARQL CLI

`slm-run` executes a SPARQL query and loads the custom functions declared in the
configuration file.

Common options:

- `--config config.ini`: load GGF associations.
- `-f path/to/query.sparql`: execute a query from a file.
- `-q "SELECT ..."`: execute an inline query.
- `--load data.ttl --format turtle`: load an RDF graph before running the query.
- `-o output.csv`: write query results to CSV.
- `--keep-store store.nq`: save the full RDF store as N-Quads.
- `--metrics --metrics-out metrics.json`: produce basic I/O metrics.
- `--debug`: enable debug logs.

Local GGF example:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f queries/bench/expand-ggf-demo.sparql \
  -o tmp/expand_demo.csv
```

MetaQA example with an explicitly loaded graph:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f xp-ggf-script/queries/metaqa-expand.sparql \
  --load data/metaqa/MetaQA/kb.ttl --format turtle \
  -o xp-ggf-script/out/metaqa_expand.csv
```

RML example:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f queries/bench/rml-ggf-demo.sparql \
  -o tmp/rml_ggf_demo.csv
```

## Available GGFs

The effective function associations are listed in [`config.ini`](config.ini).
The benchmarked graph-oriented functions include:

- `ggf:LOAD`: load an RDF file into a named graph.
- `ggf:EXPAND`: extract a neighborhood around an entity.
- `ggf:PATHS`: materialize paths between two entities.
- `ggf:SIMRANK`: compute related candidates with SimRank.
- `ggf:RANDOM-SAMPLE`: sample a subgraph.
- `ggf:CBD`: build a Concise Bounded Description.
- `ggf:SUMMARY`: produce an entity-centered graph summary.
- `ggf:LOCAL-SCHEMA`: extract a local schema around an entity.
- `ggf:COMPARE-GRAPHS`: compare two already materialized graphs.
- `ggf:CONSTRUCT`: materialize the result of a `CONSTRUCT` query or inline RDF.
- `ggf:RML`: transform JSON through an RML mapping.
- `ggf:SHACL-VALIDATE`: validate a graph with SHACL shapes.

Additional functions exist for local files, Wikidata, FAISS, LLM calls, MCP
tools, and older experiments.

## GGF vs Script Comparison

The [`xp-ggf-script/`](xp-ggf-script/) directory contains the main benchmark
workspace. It compares two execution styles:

- `GGF`: compact SPARQL queries where intermediate graphs stay inside the RDF engine.
- `script`: explicit Python orchestration, using a local HTTP SPARQL endpoint by default.

For detailed benchmark documentation, available cases, output files, plotting
commands, and MetaQA-specific notes, see
[`xp-ggf-script/README.md`](xp-ggf-script/README.md).

Short run:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand paths simrank
```

Run with explicit HTTP access for the script baseline:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand local_schema entity_similarity_compare \
  --script-access http
```

Default outputs:

- `xp-ggf-script/out/ggf_vs_script_eval.json`
- `xp-ggf-script/out/ggf_vs_script_eval.csv`
- `xp-ggf-script/out/ggf_vs_script_eval.png`

Runner cases:

- `expand`
- `paths`
- `simrank`
- `random_sample`
- `local_schema`
- `metaqa_2hop_local`
- `metaqa_anchor_search_rerank_local`
- `cbd_esbm_summary`
- `entity_similarity_compare`
- `entity_similarity_score_only`

The shortcuts `all-local` and `all` are also supported.

## Main Scripts

- [`xp-ggf-script/evaluate_ggf_vs_script.py`](xp-ggf-script/evaluate_ggf_vs_script.py): main GGF vs script benchmark runner.
- [`xp-ggf-script/plot_metaqa_scaling_summary.py`](xp-ggf-script/plot_metaqa_scaling_summary.py): plot generation from MetaQA reports.
- [`xp-ggf-script/build_metaqa_anchor_faiss.py`](xp-ggf-script/build_metaqa_anchor_faiss.py): build a local FAISS index for MetaQA entities.
- [`scripts/mini_rdflib_sparql_server.py`](scripts/mini_rdflib_sparql_server.py): local HTTP SPARQL endpoint used by script baselines.
- [`scripts/evaluate_ggf_vs_script.py`](scripts/evaluate_ggf_vs_script.py): compatibility wrapper for the main runner.
- [`scripts/evaluate_esbm_baselines.py`](scripts/evaluate_esbm_baselines.py): simple ESBM baselines.
- [`scripts/evaluate_esbm_orchestrated_baseline.py`](scripts/evaluate_esbm_orchestrated_baseline.py): client-side orchestrated ESBM baseline.
- [`scripts/evaluate_esbm_ggf.py`](scripts/evaluate_esbm_ggf.py): ESBM GGF evaluation.
- [`scripts/run_esbm_benchmark.py`](scripts/run_esbm_benchmark.py): consolidated runner for ESBM experiments.

Other scripts cover web, FAISS, Wikidata, MCP, and LLM experiments. Depending
on the script, they may require a local service, a public endpoint, or API keys.

## Useful Queries

Simple GGF examples:

- [`queries/bench/expand-ggf-demo.sparql`](queries/bench/expand-ggf-demo.sparql)
- [`queries/bench/paths-ggf-demo.sparql`](queries/bench/paths-ggf-demo.sparql)
- [`queries/bench/simrank-ggf-demo.sparql`](queries/bench/simrank-ggf-demo.sparql)
- [`queries/bench/filter-subgraph-ggf-demo.sparql`](queries/bench/filter-subgraph-ggf-demo.sparql)
- [`queries/bench/rml-ggf-demo.sparql`](queries/bench/rml-ggf-demo.sparql)

MetaQA benchmark queries:

- [`xp-ggf-script/queries/metaqa-expand.sparql`](xp-ggf-script/queries/metaqa-expand.sparql)
- [`xp-ggf-script/queries/metaqa-paths.sparql`](xp-ggf-script/queries/metaqa-paths.sparql)
- [`xp-ggf-script/queries/metaqa-simrank.sparql`](xp-ggf-script/queries/metaqa-simrank.sparql)
- [`xp-ggf-script/queries/metaqa-random-sample.sparql`](xp-ggf-script/queries/metaqa-random-sample.sparql)
- [`xp-ggf-script/queries/metaqa-local-schema.sparql`](xp-ggf-script/queries/metaqa-local-schema.sparql)
- [`xp-ggf-script/queries/metaqa-summary.sparql`](xp-ggf-script/queries/metaqa-summary.sparql)
- [`xp-ggf-script/queries/metaqa-entity-similarity.sparql`](xp-ggf-script/queries/metaqa-entity-similarity.sparql)

## Practical Notes

- Local MetaQA examples mainly use `data/metaqa/MetaQA/kb.ttl`.
- Queries under `xp-ggf-script/queries/` often expect the graph to be loaded with `--load`.
- The runner's HTTP script mode uses [`scripts/mini_rdflib_sparql_server.py`](scripts/mini_rdflib_sparql_server.py).
- LLM, web, Wikidata, MCP, and FAISS examples may require additional configuration.
- Plot documentation is available in [`xp-ggf-script/PLOTS.md`](xp-ggf-script/PLOTS.md).

## Tests

```bash
pytest -q
```

Some tests or examples may depend on external services, local models, or
environment variables. For a quick local check, prefer a targeted test or a
local GGF query.

## Status

This repository is a development and experimentation workspace. Scripts and
queries are not all at the same stability level. The most documented paths for
reproducing current experiments are [`xp-ggf-script/`](xp-ggf-script/) and
[`queries/bench/`](queries/bench/).

## License

No root `LICENSE` file was found in the inspected repository tree. The MetaQA
dataset has its own license in
[`data/metaqa/MetaQA/LICENSE.txt`](data/metaqa/MetaQA/LICENSE.txt).
