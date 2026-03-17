# Scripts README

## LangChain + Wikidata direct

Script: `scripts/langchain_wikidata_direct.py`

Ce script reproduit le pipeline de `queries/entitysearch/wikidata-summarize-prompt.sparql` en Python/LangChain:

1. generation de noms d'auteurs via LLM
2. recherche d'entites sur Wikidata (`wbsearchentities`)
3. selection de la meilleure entite via LLM
4. schema walk 1-hop via `query.wikidata.org/sparql`
5. resume final via LLM

## Prerequis

- Environnement Python du projet:

```bash
source /Users/molli-p/SPARQLLM/venv/bin/activate
```

- Pour Groq: cle API definie dans l'environnement OU dans `.env`.

Exemple `.env`:

```bash
export GROQ_API_KEY="..."
```

Note: le script charge `.env` automatiquement, pas besoin de `source .env`.

## Lancement rapide (Groq)

Commande minimale:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/langchain_wikidata_direct.py \
  --provider groq \
  --topic "well-known science-fiction authors" \
  --language en \
  --count 10 \
  --out out_wikidata_langchain_groq.json
```

Commande test courte:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/langchain_wikidata_direct.py \
  --provider groq \
  --topic "well-known science-fiction authors" \
  --language en \
  --count 1
```

## Lancement rapide (Ollama)

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/langchain_wikidata_direct.py \
  --provider ollama \
  --model "llama3.1:8b" \
  --topic "well-known science-fiction authors" \
  --language en \
  --count 10
```

## Options principales

```text
--provider   ollama | groq
--model      nom du modele (optionnel, sinon pris depuis config.ini)
--topic      sujet pour generer/ranker les entites
--language   langue Wikidata (ex: en, fr)
--count      nombre d'entites a traiter
--out        fichier de sortie JSON
--config     chemin vers config.ini (defaut: config.ini)
--env-file   chemin du .env (defaut: .env)
```

## Defaults utilises depuis `config.ini`

- `[Requests] SLM-GROQ-MODEL`
- `[Requests] SLM-OLLAMA-MODEL`
- `[Requests] SLM-LLM-TEMPERATURE`
- `[ApiKeys] GROQ_API_KEY` (fallback si absent de l'environnement)

## Erreurs courantes

- `GROQ_API_KEY is not set`:
  - verifier que `.env` existe a la racine du projet et contient `GROQ_API_KEY`
  - ou exporter la variable dans le shell
- Erreur reseau Wikidata:
  - reessayer plus tard (endpoint public)

## ESBM baselines simples (random + degree/frequency)

Script: `scripts/evaluate_esbm_baselines.py`

Objectif: evaluer des baselines entity summarization simples sur un benchmark type ESBM.

Baselines implementees:

- `random`: selection aleatoire de `k` triples candidats
- `degree`: priorise les predicates rares (score = `1/freq(predicate)`), puis prend top-`k`

Formats d'entree:

- `--graph`: fichier RDF (ttl, nt, nq, trig, rdf/xml, json-ld)
- `--gold`: verite terrain des summaries, formats supportes:
  - JSON: `{ "<entity>": [[s,p,o], ...], ... }`
  - JSONL: `{ "entity": "...", "triples": [[s,p,o], ...] }`
  - CSV: colonnes `entity,s,p,o`

Commande exemple:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/evaluate_esbm_baselines.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --baselines random degree \
  --neighborhood out \
  --out-json out/esbm_baselines_results.json
```

Sortie:

- JSON avec:
  - micro et macro precision/recall/f1
  - detail par entite
  - config d'execution

## ESBM baseline non-GGF orchestree

Script: `scripts/evaluate_esbm_orchestrated_baseline.py`

Objectif: simuler un pipeline non-GGF en 2 etapes:

1. extraction des triples candidats avec SPARQL `SELECT`
2. selection/ranking dans Python (`random` ou `degree`)

Ce script produit les memes metriques qualite (P/R/F1), plus des metriques de cout d'orchestration:

- nombre de requetes SPARQL
- temps total des requetes candidats
- volume de triples extraits
- estimation de payload transfere (bytes)

Commande exemple:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/evaluate_esbm_orchestrated_baseline.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --baselines random degree \
  --neighborhood out \
  --out-json out/esbm_orchestrated_baselines_results.json
```

## Runner benchmark consolide (simple + orchestre + ggf optionnel)

Script: `scripts/run_esbm_benchmark.py`

Objectif: lancer en une commande les baselines ESBM et produire un rapport consolide.

Sorties:

- `benchmark_report.json`: rapport complet (config, temps, resultats)
- `summary.csv`: table plate (micro/macro P/R/F1) prete pour analyse/plot

Commande exemple:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/run_esbm_benchmark.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --baselines random degree \
  --neighborhood out \
  --out-dir out/esbm-benchmark
```

Ajouter des resultats GGF pre-calcules:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/run_esbm_benchmark.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --baselines random degree \
  --neighborhood out \
  --out-dir out/esbm-benchmark \
  --ggf-results-json out/esbm_ggf_results.json
```

Lancer la baseline GGF directement depuis le runner:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/run_esbm_benchmark.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --baselines random degree \
  --neighborhood out \
  --out-dir out/esbm-benchmark \
  --run-ggf \
  --ggf-modes degree random \
  --config config.ini
```

Quand plusieurs modes sont fournis, le runner produit un fichier par mode:

- `ggf_baseline_degree.json`
- `ggf_baseline_random.json`

## ESBM GGF (meme logique que la baseline script)

Nouvelle GGF: `ggf:ESBM-SUMMARY(g_source, entity, k, neighborhood, mode, seed)`

- `mode=degree`: score des triples par rarete du predicat (`1/freq(predicate)`), top-k
- `mode=random`: echantillonnage aleatoire top-k avec seed

Requete de demo:

- `queries/bench/esbm-ggf-summary.sparql`
- `queries/bench/cbd-esbm-summary.sparql` — composition `CBD -> ESBM-SUMMARY` compatible ESBM

Script d'evaluation dedie GGF:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/evaluate_esbm_ggf.py \
  --graph data/mixed-events.ttl \
  --gold data/esbm_gold.csv \
  --k 10 \
  --neighborhood out \
  --mode degree \
  --seed 42 \
  --config config.ini \
  --out-json out/esbm_ggf_results.json
```

## Comparaison cible: CBD + ESBM-SUMMARY, GGF vs script data shipping

Script: `scripts/compare_cbd_esbm_summary.py`

Objectif:

- cote GGF: compter seulement `query input bytes + final result bytes`
- cote script: compter `toutes les requetes Wikidata + toutes les reponses + final result bytes`
- verifier que les triples produits sont identiques

Commande exemple:

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/compare_cbd_esbm_summary.py \
  --entity http://www.wikidata.org/entity/Q42 \
  --lang en \
  --k 10 \
  --neighborhood both \
  --mode degree \
  --seed 42 \
  --config config.ini \
  --out-json out/cbd_esbm_compare.json
```

## Local-store credibility experiment (English)

This section shows how to run the similarity benchmark in a fully local mode,
so that intermediate graphs are not fetched from Wikidata at runtime.

### Goal

Measure client-side transfer and call scaling for:

- GGF pipeline (single SPARQL query, intermediate graphs stay server-side)
- Script pipeline (iterative client orchestration)

for candidate limits `10 -> 20 -> 30`.

### Step 1: Build a local RDF snapshot (one-time ingestion)

This fetches Q42 + a pool of SF writer candidates and stores them in one Turtle file.

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/build_similarity_local_snapshot.py \
  --ref-entity http://www.wikidata.org/entity/Q42 \
  --max-limit 30 \
  --lang en \
  --out-ttl tmp/sf_similarity_snapshot.ttl \
  --out-json tmp/sf_similarity_snapshot.json
```

Outputs:

- `tmp/sf_similarity_snapshot.ttl`: local store snapshot
- `tmp/sf_similarity_snapshot.json`: ingestion metrics (calls/bytes)

### Step 2: Run local transfer scaling experiment (GGF vs script)

This runs both methods locally for limits 10, 20, and 30.

```bash
/Users/molli-p/SPARQLLM/venv/bin/python scripts/experiment_similarity_transfer_scaling_local.py \
  --snapshot-ttl tmp/sf_similarity_snapshot.ttl \
  --limits 10 20 30 \
  --out-csv tmp/similarity_transfer_scaling_local.csv \
  --out-json tmp/similarity_transfer_scaling_local.json \
  --out-plot plots/similarity_transfer_scaling_local.png
```

Outputs:

- `tmp/similarity_transfer_scaling_local.csv`: summary table by method and limit
- `tmp/similarity_transfer_scaling_local.json`: full metrics payload
- `plots/similarity_transfer_scaling_local.png`: transfer and call scaling plot

### Optional: run the GGF query directly with CLI metrics

```bash
/Users/molli-p/SPARQLLM/venv/bin/python -m SPARQLLM.cli.slm \
  --config config.ini \
  -f queries/bench/entity-similarity-compare-ggf.sparql \
  -o tmp/entity_similarity_compare.csv \
  --metrics \
  --metrics-out tmp/entity_similarity_compare_metrics.json
```

### Repro notes

- Keep `--mode degree --k 10 --neighborhood both --seed 42` fixed across runs.
- Treat snapshot build as ingestion cost, and scaling experiment as execution cost.
- In local mode, runtime analysis does not call Wikidata.
