# xp-ggf-script

Experiment workspace dedicated to the `GGF vs script` comparison, kept as isolated as possible from the rest of the repository.

This folder is now centered on a single dataset for the examples and benchmark cases exposed here:

- `MetaQA`

## Goal

Compare two execution styles over the same graph operations:

- `GGF`: a compact SPARQL query, with intermediate graphs kept inside the engine
- `script`: explicit Python orchestration; by default it now reaches the KB through a local HTTP SPARQL endpoint backed by RDFLib over `kb.ttl`, so the benchmark measures actual HTTP calls and transferred bytes on the script side

For the benchmark runner itself, the GGF side now preloads the KB through the CLI `--load` option rather than calling `ggf:LOAD(...)` inside the generated benchmark query. This matters for timing:

- the KB parsing / TTL loading time is tracked separately by the CLI
- the reported `ggf_wall_time_s` now reflects query execution only
- this makes the GGF wall time more comparable to the script-side orchestration time

The standalone `.sparql` files under `queries/` follow the same model: they expect the KB to be provided through CLI `--load`, and the entity-centric operators resolve the current loaded graph implicitly.

For the planned local search / rerank benchmark, a persistent FAISS index over
MetaQA anchor entities can be built once and reused across runs:

```bash
python xp-ggf-script/build_metaqa_anchor_faiss.py \
  --kb data/metaqa/MetaQA/kb.ttl \
  --qa data/metaqa/MetaQA/qa_2hop.ttl \
  --out-dir xp-ggf-script/data/metaqa_anchor_faiss
```

Once the index exists, the new local `search + rerank` benchmark case can be run with:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases metaqa_anchor_search_rerank_local \
  --metaqa-anchor-faiss-dir xp-ggf-script/data/metaqa_anchor_faiss \
  --metaqa-limit 100
```

This case uses MetaQA questions, searches the persistent local FAISS index with
the anchor label, reranks candidates with the local LLM, and compares GGF vs
script mainly through transferred intermediate bytes and logical call counts.

At the moment, this folder contains two kinds of artifacts:

- benchmarked queries and runner cases used by `evaluate_ggf_vs_script.py`
- standalone SHACL validation examples that are documented and runnable, but not yet included in the benchmark runner

The main runner produces:

- a detailed JSON report
- a summary CSV
- a comparison PNG

## GGF Operators Used In This XP

Most operators used here return a named graph URI. In practice, the usual pattern is:

```sparql
BIND(ggf:OPERATOR(...) AS ?gOut)
GRAPH ?gOut {
  ...
}
```

Here are the main graph-oriented functions used in this experiment.

- `ggf:LOAD(path)`
  Signature: `ggf:LOAD("path/to/file.ttl") -> graph URI`
  Input: local RDF file path
  Output: named graph loaded into the shared store
  Note: the XP queries in this folder no longer call `ggf:LOAD(...)` directly; they rely on CLI `--load` instead

- `ggf:EXPAND(entity_iri, hops=1, direction="both")`
  Signature: `ggf:EXPAND(<entity>, 1, "both") -> graph URI`
  Input: a center entity, a hop depth, and a direction in `out | in | both`, resolved against the currently loaded KB
  Output: named graph containing the induced neighborhood triples around the center entity

- `ggf:FILTER-SUBGRAPH(g_source, predicate_csv="", node_csv="", node_mode="touch", keep_literals=true)`
  Signature: `ggf:FILTER-SUBGRAPH(?g, "p1,p2", "n1,n2", "induced", false) -> graph URI`
  Input: an explicit source graph plus optional predicate and node constraints
  Output: named graph containing only the filtered triples, plus a small metadata node with the triple count
  Note: this helper exists in the codebase but is not part of the `xp-ggf-script` benchmark anymore

- `ggf:PATHS(start_iri, goal_iri, max_depth=4, direction="out", max_paths=10)`
  Signature: `ggf:PATHS(<start>, <goal>, 4, "both", 10) -> graph URI`
  Input: a start node, a goal node, and path search limits, resolved against the currently loaded KB
  Output: named graph encoding shortest paths with one `slm:PathSet` root:
  `slm:start`, `slm:goal`, `slm:pathCount`, `slm:hasPath`; each `slm:Path` has
  `slm:rank`, `slm:length`, `slm:hasStep`; each `slm:PathStep` has `slm:pos`,
  `slm:src`, `slm:pred`, and `slm:dst`

- `ggf:SIMRANK(center_iri, decay=0.8, max_iter=5, top_k=10, max_nodes=200)`
  Signature: `ggf:SIMRANK(<center>, 0.8, 5, 10, 200) -> graph URI`
  Input: a center node and SimRank hyperparameters, resolved against the currently loaded KB
  Output: named graph containing a `cand:SimRankResult` root and ranked `cand:SimRankNode` candidates with `cand:entity`, `cand:score`, and `cand:rank`

- `ggf:RANDOM-SAMPLE(entity_iri, hops=1, direction="both", sample_rate=0.5, seed=42)`
  Signature: `ggf:RANDOM-SAMPLE(<entity>, 1, "both", 0.5, 42) -> graph URI`
  Input: a center entity, a hop depth, a direction, a Bernoulli sample rate, and a seed, resolved against the currently loaded KB
  Output: named graph containing sampled triples plus a `cand:RandomSample` root with global cardinality estimates and per-predicate estimate nodes

- `ggf:SUMMARY(g_source, entity_iri, k=10, neighborhood="out", mode="degree", seed=42)`
  Signature: `ggf:SUMMARY(?g, <entity>, 10, "both", "degree", 42) -> graph URI`
  Input: a source named graph, a center entity, a summary size `k`, a neighborhood mode, and a ranking mode in `degree | random`
  Output: named graph containing only the selected summary triples for that entity

- `ggf:LOCAL-SCHEMA(entity_iri, hops=1, direction="both", max_examples=3)`
  Signature: `ggf:LOCAL-SCHEMA(<entity>, 2, "both", 3) -> graph URI`
  Input: a center entity, a hop depth, a direction, and an example cap, resolved against the currently loaded KB
  Output: named graph containing a `cand:LocalSchema` root and ranked `cand:SchemaSlot` nodes with `cand:hopCount`, `cand:direction`, `cand:property`, `cand:frequency`, and a few `cand:exampleNeighbor` / `cand:exampleLiteral` values

- `ggf:COMPARE-GRAPHS(g1, g2, e1, e2)`
  Signature: `ggf:COMPARE-GRAPHS(?g1, ?g2, <entity1>, <entity2>) -> graph URI`
  Input: two already materialized named graphs and their corresponding center entities
  Output: named graph containing a `cand:Comparison` root with `cand:sharedCount`, `cand:differingCount`, `cand:exclusiveCount`, and `cand:similarityScore`, plus property-level comparison nodes

- `ggf:CBD(entity_iri, lang="en")`
  Signature: `ggf:CBD(<entity>, "en") -> graph URI`
  Input: an entity IRI
  Output: in local mode, a CBD built from the currently loaded KB; without a loaded KB, the legacy Wikidata-oriented fallback is still available
  Note: `cbd_esbm_summary` now uses `CBD + SUMMARY` again

- `ggf:SHACL-VALIDATE(g_data, shape_file_or_graph)`
  Signature: `ggf:SHACL-VALIDATE(?g, "path/to/shape.ttl") -> graph URI`
  Input: a named data graph and either a SHACL file path or a named graph holding shapes
  Output: named graph containing the SHACL report, including a `cand:ShaclReport` metadata node and optional `sh:ValidationResult` nodes

## Contents

- `evaluate_ggf_vs_script.py`: main benchmark runner
- `plot_metaqa_scaling_summary.py`: plotting helper for MetaQA outputs
- `PLOTS.md`: dedicated guide to the generated PNG plots
- `queries/`: reference SPARQL queries for the GGF side
- `shapes/`: SHACL shapes used by validation examples
- `out/`: benchmark outputs
- `tmp/`: local temporary files and caches for the benchmark

## Queries

Benchmarked queries:

- `queries/metaqa-expand.sparql`
- `queries/metaqa-paths.sparql`
- `queries/metaqa-simrank.sparql`
- `queries/metaqa-random-sample.sparql`
- `queries/metaqa-summary.sparql`
- `queries/metaqa-local-schema.sparql`
- `queries/metaqa-entity-similarity.sparql`

Standalone SHACL examples:

- `queries/metaqa-expand-shacl-validate.sparql`
- `queries/metaqa-expand-shacl-violation.sparql`

## Runner Cases

- `expand`
- `paths`
- `simrank`
- `random_sample`
- `local_schema`
- `cbd_esbm_summary`
- `entity_similarity_compare`
- `entity_similarity_score_only`
- `metaqa_2hop_local`

The `cbd_esbm_summary` and `entity_similarity_compare` cases now use `ggf:SUMMARY(...)`.
The `entity_similarity_score_only` runner case mirrors [`queries/bench/metaqa-entity-similarity-score-only.sparql`](/Users/molli-p/SPARQLLM/queries/bench/metaqa-entity-similarity-score-only.sparql) with a script baseline.
The `local_schema` runner case uses `--schema-hops 2` by default, to match the reference query.
The entity-centric operators above also still accept the older graph-first form for backward compatibility.
The SHACL validation queries are not part of the runner yet.

## MetaQA Examples Used

- `ment:taxidermia` for `expand`, `simrank`, `random-sample`, `summary`, and `local-schema`
- `ment:taxidermia` also for the standalone SHACL validation examples
- `ment:avatar` and `ment:titanic` for `paths`
- `ment:avatar` against a broader MetaQA movie pool for `entity_similarity_compare`
- `ment:avatar` against 2009 candidates for `entity_similarity_score_only`

## Useful Commands

Run a few local cases:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand paths simrank
```

Run the script side through the HTTP SPARQL endpoint explicitly:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand local_schema entity_similarity_compare \
  --script-access http
```

Add a fixed artificial latency to each script-side HTTP call:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases simrank \
  --script-access http \
  --http-latency-ms 5
```

Enable more detailed progress logs:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand local_schema \
  --script-access http \
  --verbose
```

Run all local cases plus MetaQA 2-hop:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases all-local
```

Run those plus `summary` and `entity_similarity_compare`:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases all
```

Run `entity_similarity_compare` as a scaling sweep with candidate limits `10 50 100`:

```bash
./xp-ggf-script/run_entity_similarity_scaling.sh
```

Or directly with the runner:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases entity_similarity_compare \
  --script-access http \
  --candidate-limit 50
```

Run the current full HTTP benchmark with a small artificial network latency:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases all \
  --script-access http \
  --metaqa-limit 100 \
  --http-latency-ms 5
```

Run one GGF query directly:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f xp-ggf-script/queries/metaqa-summary.sparql \
  --load data/metaqa/MetaQA/kb.ttl --format turtle \
  -o xp-ggf-script/out/metaqa_summary.csv
```

Validate an expanded graph with SHACL:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f xp-ggf-script/queries/metaqa-expand-shacl-validate.sparql \
  --load data/metaqa/MetaQA/kb.ttl --format turtle \
  -o xp-ggf-script/out/metaqa_expand_shacl_validate.csv
```

Run the negative SHACL example and inspect explicit violations:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f xp-ggf-script/queries/metaqa-expand-shacl-violation.sparql \
  --load data/metaqa/MetaQA/kb.ttl --format turtle \
  -o xp-ggf-script/out/metaqa_expand_shacl_violation.csv
```

Plot MetaQA results:

```bash
python xp-ggf-script/plot_metaqa_scaling_summary.py \
  --inputs xp-ggf-script/out/metaqa_20.json xp-ggf-script/out/metaqa_50.json
```

## Outputs

By default:

- JSON: `xp-ggf-script/out/ggf_vs_script_eval.json`
- CSV: `xp-ggf-script/out/ggf_vs_script_eval.csv`
- PNG: `xp-ggf-script/out/ggf_vs_script_eval.png`

The runner also writes its temporary files and matplotlib caches to:

- `xp-ggf-script/tmp/`

Plot documentation:

- [`xp-ggf-script/PLOTS.md`](/Users/molli-p/SPARQLLM/xp-ggf-script/PLOTS.md)

For the `random_sample` case, the JSON and CSV summaries also include:

- `exact_cardinality`
- `estimated_cardinality`
- `cardinality_absolute_error`
- `cardinality_relative_error`

## Script-side Access Model

The default mode is now:

- `--script-access http`

In that mode, the runner starts a local HTTP SPARQL endpoint backed by:

- `scripts/mini_rdflib_sparql_server.py`

The endpoint serves the file passed through:

- `--graph`

For the current XP, that is normally:

- `data/metaqa/MetaQA/kb.ttl`

For the `metaqa_2hop_local` case, the question file is still read directly by the runner from:

- `--metaqa-qa`

This means the `script` baseline no longer reads triples directly from an in-memory RDFLib graph by default. Instead, it issues standard SPARQL `SELECT` requests over HTTP and measures:

- `logical_call_count`: number of HTTP requests sent by the script baseline
- `upload_bytes`: request bytes sent to the local SPARQL endpoint
- `download_bytes`: response bytes received from the local SPARQL endpoint
- `output_bytes`: normalized benchmark result bytes written in the report
- `transfer_total_bytes`: `upload_bytes + download_bytes + output_bytes`

You can optionally make the script-side wall time harsher, and usually fairer, with:

- `--http-latency-ms`

This adds a fixed latency to every script-side HTTP SPARQL request. It does not affect transfer metrics and it does not affect the GGF side.

For extra runtime details, the runner also supports:

- `--verbose`

In verbose mode, the runner prints extra information about GGF subqueries and
per-side metrics for each case, in addition to the standard progress logs.

The older mode is still available:

- `--script-access local`

That mode is still useful for debugging or for comparing the old approximation against the HTTP-based measurement.

## Dependencies

The benchmark first tries to use `SPARQLLM` as an installed Python dependency.
If that is not available, it falls back to the local checkout in this repository.

MetaQA inputs can be overridden with:

- `--metaqa-kb`
- `--metaqa-qa`
- `--graph`

## Compatibility

The old entry points are still kept as wrappers:

- [`scripts/evaluate_ggf_vs_script.py`](/Users/molli-p/SPARQLLM/scripts/evaluate_ggf_vs_script.py)
- [`scripts/plot_metaqa_scaling_summary.py`](/Users/molli-p/SPARQLLM/scripts/plot_metaqa_scaling_summary.py)

## Current Status

- The benchmarked queries in `xp-ggf-script/queries/` are MetaQA-only.
- The SHACL validation queries are MetaQA-only standalone examples.
- The recommended summarization name is `SUMMARY`.
- The old name `ESBM-SUMMARY` is still supported as a backward-compatibility alias.
- `filter_subgraph` is no longer part of the XP benchmark.
- The file `data/simrank-demo.ttl` is still present in this folder, but it is no longer central to the current experiment queries.
