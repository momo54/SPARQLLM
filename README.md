# SPARQLLM

Ce depot contient du code experimental autour de l'execution de fonctions de
graphe dans SPARQL. Le point central est l'usage de Graph Generating Functions
(GGF), c'est-a-dire de fonctions SPARQL personnalisees qui materialisent un
graphe nomme intermediaire, puis le rendent interrogeable dans la meme requete.

Le depot contient aussi des scripts Python qui servent de points de comparaison
ou d'outils d'experimentation. Ces scripts orchestrent les memes operations cote
client afin de comparer, selon les cas, le temps d'execution, le nombre d'appels
logiques et le volume de donnees transfere.

## Principe GGF

Les fonctions declarees dans [`config.ini`](config.ini) sont enregistrees sous
le prefixe `http://ggf.org/`. Une requete GGF suit generalement ce modele:

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

La fonction retourne l'IRI d'un graphe nomme. Les triplets produits restent dans
le store RDF et peuvent etre interroges ou passes a une autre GGF.

## Organisation

- [`SPARQLLM/`](SPARQLLM/): package Python, CLI et implementations des UDF/GGF.
- [`SPARQLLM/udf/`](SPARQLLM/udf/): fonctions SPARQL personnalisees.
- [`queries/`](queries/): requetes d'exemple par domaine.
- [`queries/bench/`](queries/bench/): exemples GGF isoles et requetes de benchmark.
- [`xp-ggf-script/`](xp-ggf-script/): espace principal pour les comparaisons GGF vs scripts sur MetaQA.
- [`scripts/`](scripts/): scripts Python d'evaluation, de conversion, de plots et de baselines.
- [`data/`](data/): jeux de donnees locaux et index utilises par les exemples.
- [`tests/`](tests/): tests du projet.

## Installation

Le paquet indique Python `>=3.12` dans [`setup.py`](setup.py).

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

La commande principale est ensuite disponible via:

```bash
slm-run --help
```

Il est aussi possible d'utiliser le module directement:

```bash
python -m SPARQLLM.cli.slm --help
```

## Commande SPARQL

`slm-run` execute une requete SPARQL et charge les fonctions declarees dans le
fichier de configuration.

Options courantes:

- `--config config.ini`: charge les associations GGF.
- `-f path/to/query.sparql`: execute une requete depuis un fichier.
- `-q "SELECT ..."`: execute une requete passee en ligne de commande.
- `--load data.ttl --format turtle`: charge un graphe RDF avant la requete.
- `-o output.csv`: ecrit les resultats dans un fichier CSV.
- `--keep-store store.nq`: sauvegarde le store RDF complet en N-Quads.
- `--metrics --metrics-out metrics.json`: produit des metriques d'entree/sortie.
- `--debug`: active les logs de debug.

Exemple local avec une GGF de voisinage:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f queries/bench/expand-ggf-demo.sparql \
  -o tmp/expand_demo.csv
```

Exemple MetaQA avec chargement explicite du graphe:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f xp-ggf-script/queries/metaqa-expand.sparql \
  --load data/metaqa/MetaQA/kb.ttl --format turtle \
  -o xp-ggf-script/out/metaqa_expand.csv
```

Exemple RML:

```bash
python -m SPARQLLM.cli.slm --config config.ini \
  -f queries/bench/rml-ggf-demo.sparql \
  -o tmp/rml_ggf_demo.csv
```

## GGF disponibles

Les associations effectives sont dans [`config.ini`](config.ini). Parmi les
fonctions utilisees dans les benchmarks:

- `ggf:LOAD`: charge un fichier RDF dans un graphe nomme.
- `ggf:EXPAND`: extrait un voisinage autour d'une entite.
- `ggf:PATHS`: materialise des chemins entre deux entites.
- `ggf:SIMRANK`: calcule des candidats proches par SimRank.
- `ggf:RANDOM-SAMPLE`: echantillonne un sous-graphe.
- `ggf:CBD`: construit une Concise Bounded Description.
- `ggf:SUMMARY`: produit un resume de graphe centre sur une entite.
- `ggf:LOCAL-SCHEMA`: extrait un schema local autour d'une entite.
- `ggf:COMPARE-GRAPHS`: compare deux graphes deja materialises.
- `ggf:CONSTRUCT`: materialise le resultat d'un `CONSTRUCT` ou du RDF inline.
- `ggf:RML`: transforme du JSON via un mapping RML.
- `ggf:SHACL-VALIDATE`: valide un graphe avec des shapes SHACL.

D'autres fonctions existent pour les fichiers locaux, Wikidata, FAISS, LLM,
MCP et des experimentations plus anciennes.

## Comparaison GGF vs scripts

Le dossier [`xp-ggf-script/`](xp-ggf-script/) regroupe le benchmark principal.
Il compare deux styles d'execution:

- `GGF`: une requete SPARQL compacte; les graphes intermediaires restent dans le moteur RDF.
- `script`: une orchestration Python explicite; par defaut, elle interroge un endpoint SPARQL HTTP local.

Commande courte:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand paths simrank
```

Commande avec acces script via HTTP explicite:

```bash
python xp-ggf-script/evaluate_ggf_vs_script.py \
  --config config.ini \
  --cases expand local_schema entity_similarity_compare \
  --script-access http
```

Sorties par defaut:

- `xp-ggf-script/out/ggf_vs_script_eval.json`
- `xp-ggf-script/out/ggf_vs_script_eval.csv`
- `xp-ggf-script/out/ggf_vs_script_eval.png`

Cas reconnus par le runner:

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

Les raccourcis `all-local` et `all` sont egalement supportes.

## Scripts principaux

- [`xp-ggf-script/evaluate_ggf_vs_script.py`](xp-ggf-script/evaluate_ggf_vs_script.py): runner principal GGF vs script.
- [`xp-ggf-script/plot_metaqa_scaling_summary.py`](xp-ggf-script/plot_metaqa_scaling_summary.py): generation de plots a partir de rapports MetaQA.
- [`xp-ggf-script/build_metaqa_anchor_faiss.py`](xp-ggf-script/build_metaqa_anchor_faiss.py): construction d'un index FAISS local pour les entites MetaQA.
- [`scripts/mini_rdflib_sparql_server.py`](scripts/mini_rdflib_sparql_server.py): endpoint SPARQL HTTP local utilise par certaines baselines script.
- [`scripts/evaluate_ggf_vs_script.py`](scripts/evaluate_ggf_vs_script.py): wrapper de compatibilite vers le runner principal.
- [`scripts/evaluate_esbm_baselines.py`](scripts/evaluate_esbm_baselines.py): baselines ESBM simples.
- [`scripts/evaluate_esbm_orchestrated_baseline.py`](scripts/evaluate_esbm_orchestrated_baseline.py): baseline ESBM orchestree cote client.
- [`scripts/evaluate_esbm_ggf.py`](scripts/evaluate_esbm_ggf.py): evaluation de la version GGF ESBM.
- [`scripts/run_esbm_benchmark.py`](scripts/run_esbm_benchmark.py): runner consolide pour les experiences ESBM.

Plusieurs autres scripts concernent des experiences web, FAISS, Wikidata, MCP ou
LLM. Ils peuvent dependre d'un service local, d'un endpoint public ou de cles
API selon le cas.

## Requetes utiles

Requetes GGF simples:

- [`queries/bench/expand-ggf-demo.sparql`](queries/bench/expand-ggf-demo.sparql)
- [`queries/bench/paths-ggf-demo.sparql`](queries/bench/paths-ggf-demo.sparql)
- [`queries/bench/simrank-ggf-demo.sparql`](queries/bench/simrank-ggf-demo.sparql)
- [`queries/bench/filter-subgraph-ggf-demo.sparql`](queries/bench/filter-subgraph-ggf-demo.sparql)
- [`queries/bench/rml-ggf-demo.sparql`](queries/bench/rml-ggf-demo.sparql)

Requetes MetaQA du benchmark:

- [`xp-ggf-script/queries/metaqa-expand.sparql`](xp-ggf-script/queries/metaqa-expand.sparql)
- [`xp-ggf-script/queries/metaqa-paths.sparql`](xp-ggf-script/queries/metaqa-paths.sparql)
- [`xp-ggf-script/queries/metaqa-simrank.sparql`](xp-ggf-script/queries/metaqa-simrank.sparql)
- [`xp-ggf-script/queries/metaqa-random-sample.sparql`](xp-ggf-script/queries/metaqa-random-sample.sparql)
- [`xp-ggf-script/queries/metaqa-local-schema.sparql`](xp-ggf-script/queries/metaqa-local-schema.sparql)
- [`xp-ggf-script/queries/metaqa-summary.sparql`](xp-ggf-script/queries/metaqa-summary.sparql)
- [`xp-ggf-script/queries/metaqa-entity-similarity.sparql`](xp-ggf-script/queries/metaqa-entity-similarity.sparql)

## Notes pratiques

- Les exemples MetaQA locaux utilisent principalement `data/metaqa/MetaQA/kb.ttl`.
- Les requetes sous `xp-ggf-script/queries/` supposent souvent que le graphe est charge avec `--load`.
- Le mode script HTTP du runner utilise [`scripts/mini_rdflib_sparql_server.py`](scripts/mini_rdflib_sparql_server.py).
- Les exemples LLM, web, Wikidata, MCP ou FAISS peuvent necessiter une configuration supplementaire.
- La documentation detaillee des plots est dans [`xp-ggf-script/PLOTS.md`](xp-ggf-script/PLOTS.md).

## Tests

```bash
pytest -q
```

Certains tests ou exemples peuvent dependre de services externes, d'un modele
local ou de variables d'environnement. Pour un controle rapide, preferer un
test cible ou une requete locale GGF.

## Statut

Le depot est un espace de developpement et d'experimentation. Les scripts et les
requetes ne sont pas tous au meme niveau de stabilite. Les chemins les plus
documentes pour reproduire les experiences actuelles sont ceux de
[`xp-ggf-script/`](xp-ggf-script/) et de [`queries/bench/`](queries/bench/).

## Licence

Aucun fichier `LICENSE` racine n'a ete identifie dans l'arborescence inspectee.
Le jeu de donnees MetaQA contient sa propre licence dans
[`data/metaqa/MetaQA/LICENSE.txt`](data/metaqa/MetaQA/LICENSE.txt).
