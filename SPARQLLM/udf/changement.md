# CSV.py

## Différences entre le fichier original et le fichier modifié

- ***Original*** : Utilisation de **file:///Users/molli-p/SPARQLLM/data/results.csv** comme URI pour le fichier CSV d'entrée **(ligne 43).**
  
- ***modifié*** :Utilisation de **data/results**.csv comme URI pour le fichier CSV **(ligne 43)**.

**Raison :**
La modification permet d'utiliser un chemin générique plus adapté à l'environnement local. Cela facilite les tests sur des systèmes différents.

## Explication des choix des fonctions de test et de leur implémentation

### 1. test_valid_csv

- **Objectif** : Tester si un fichier CSV valide génère correctement un graphe RDF.
- **Méthode** :
  
  - Création d'un CSV fictif avec deux lignes et plusieurs colonnes.

  - Simulation de l'ouverture du fichier avec **mock_open**.
  
  - Vérification que :
    - Le graphe RDF n'est pas nul.
Le graphe RDF contient le bon nombre de triplets.
    - Le graphe RDF n'est pas nul.
Le graphe RDF contient le bon nombre de triplets.

**Particularité**
Le nombre attendu de triplets est basé sur le contenu du CSV (20 pour 2 lignes avec 10 colonnes).

### 2. test_csv_with_mixed_data_types

- **Objectif** : Vérifier que le typage des données dans le RDF correspond aux types des colonnes dans le CSV.
- **Méthode**:
  
  - Création d'un CSV fictif avec des colonnes de différents types : entier, flottant, booléen, chaîne.
  
  - Simulation de l'ouverture et de la lecture du fichier.
  
  - Vérification que :
    - Les valeurs RDF sont correctement typées **(integer, float, string)**.
  
**Particularité :**
Utilisation des propriétés **datatype** pour garantir le bon typage des valeurs RDF.

### 3. test_csv_with_malformed_data 

- **Objectif** : Vérifier qu'un fichier CSV mal formé ne génère pas de graphe RDF.

- **Méthode** :
  - Création d'un CSV fictif avec des lignes incomplètes ou des colonnes supplémentaires.
  - Simulation d'une erreur de parsing avec **pandas.errors.ParserError.**
  - Vérification que :
    - Aucun graphe RDF n'est généré (la fonction **retourne None**).
  
**Particularité**
Simulation de l'erreur avec **patch** pour s'assurer que le fichier est traité comme mal formé.

# funcLLM.py

## Différences entre le fichier original et le fichier modifié

### Vérification pour un prompt vide

- **Original** :
  - Aucune vérification si le prompt est vide.
  
- **Modifié** (ligne 21) :

```python
assert prompt.strip() != "", "Le prompt ne peut pas être vide."
```

**Raison** :
Un prompt vide pourrait provoquer une erreur inattendue de l'API OpenAI ou générer un comportement non défini. Cette modification permet d'éviter ces cas en bloquant immédiatement l'exécution avec une **AssertionError**.

## Explication des choix des tests unitaires

### 1. test_valid_prompt 

- **Objectif** : Vérifier que la fonction retourne un Literal RDF valide pour un prompt valide.
- **Méthode** :
  - Fournir un prompt simple ("Quelle est la capitale de la France ?").
  - Vérifier que le résultat :
    - Est une instance de **Literal**.
    - Contient "Paris" comme mot-clé (résultat attendu).

- **Particularité**: L'utilisation de **assertIn("Paris", str(result))** garantit que la réponse correspond au contexte du prompt sans être affectée par des variations exactes dans la formulation.
 
### 2. test_empty_prompt

- **Objectif** : Tester le comportement de la fonction lorsqu'un prompt vide est fourni.
  
- **Méthode** :
  - Fournir un prompt vide.
  - Vérifier qu'une **AssertionError** est levée grâce à la ligne **assert prompt.strip() != ""**.
  
**Particularité** :
Cela teste directement la nouvelle logique ajoutée pour éviter les prompts vides.

### 3. test_long_prompt

- **Objectif** : S'assurer que la fonction gère correctement des prompts très longs sans générer d'erreurs.
- **Méthode** :
  - Fournir un prompt artificiellement long (répétition de "Lorem ipsum").
  - Vérifier que le résultat :
    - Est une instance de **Literal**.
    - N'est pas vide **(len(str(result)) > 0)**.

**Particularité** :
Cela garantit que la fonction peut gérer des cas d'usage exigeants sans dépasser les limites de l'API ou rencontrer des problèmes de performance.

### 4. test_approximate_response

- **Objectif** : Tester un cas où la réponse peut varier légèrement.
- **Méthode** :
  - Fournir un prompt demandant une citation célèbre d'Albert Einstein.
  - Vérifier que la réponse contient au moins un des mots-clés liés à Einstein, comme "relativité", "imagination", ou "Einstein".

**Particularité** :
Ce test tient compte de la nature imprévisible des modèles LLM en vérifiant uniquement des mots-clés attendus, et non la réponse complète. Cela évite des échecs de test inutiles dus à des variations.

# funcSE_scrap.py

## Différences entre le fichier original et le fichier modifié

### 1. Vérification des mots-clés (keywords)

- **Original** :

- Aucune validation des mots-clés.
- Si les mots-clés sont vides ou trop longs, l'application peut se comporter de manière imprévisible ou lever des exceptions inattendues.

- **Modifié** :

  - Ajout d'une vérification pour les mots-clés vides **(ligne 23) :**

    ```python
    if not keywords.strip():
        raise ValueError("Les mots-clés ne peuvent pas être vides.")
    ```

  - Ajout d'une limite pour les mots-clés trop longs **(ligne 26) :**

    ```python
    if len(keywords) > 1000:
    raise ValueError("Les mots-clés sont trop longs.")
    ```

**Utilité** :
Ces changements permettent de gérer proprement des cas inattendus, comme des entrées vides ou excessivement longues, évitant ainsi des erreurs inutiles dans l'exécution ou dans l'interaction avec l'API Google.

### 2. Gestion des liens retournés

- **Original :**
  
  - Aucune vérification si links est vide après l'appel à engine.search.
  - Cela pourrait provoquer des erreurs si aucun résultat n’est trouvé pour les mots-clés.

- **Modifié :**
  - Vérification que **links** n'est pas vide **(ligne 29)** :

    ```python
    if not links:
        raise ValueError("Aucun lien trouvé pour les mots-clés.")
    ```

**Utilité** :

Cette modification garantit que la fonction lève une exception explicite si aucun lien n’est trouvé, au lieu de provoquer une erreur imprévisible.

###  3. Gestion des erreurs

- **Original** :
  - Aucune gestion explicite des exceptions.
- **Modifié** :
  - Ajout d’un bloc try-except pour gérer les erreurs éventuelles **(lignes 28-32)** :

  ```python
    try:
        results = engine.search(keywords, pages=1)
        links = results.links()
        if not links:
            raise ValueError("Aucun lien trouvé pour les mots-clés.")
        return URIRef(links[0])
    except Exception as e:
    logger.error(f"Erreur lors de la recherche : {e}")
    raise
    ```

**Utilité** :
Cela permet de capturer et de consigner toutes les exceptions, améliorant ainsi la traçabilité et facilitant le débogage.

## Explication des choix des tests unitaires

### 1. test_valid_keywords

- **Objectif** : Tester un cas normal où des mots-clés valides sont fournis.

- **Méthode** :

  - Fournir des mots-clés valides ("university of nantes").
  - Vérifier que :
    - Le retour est de type **URIRef**.
    - L'URI retournée est valide **(is_valid_uri(result))**.
  
**Particularité**: Il s’assure que la fonction fonctionne comme prévu avec des entrées normales.

### 2. test_empty_keywords

- **Objectif** : Vérifier que la fonction lève une exception lorsqu'un mot-clé vide est fourni.
  
- **Méthode** :

  - Fournir un mot-clé vide (**keywords = ""**).
  - Vérifier que la fonction lève une **ValueError** avec le message approprié.

**Particularité** Il vérifie la robustesse de la validation des entrées, introduite dans la ligne 23 du fichier modifié.

### 3. test_long_keywords

- **Objectif** : Tester le comportement de la fonction lorsqu’un mot-clé trop long est fourni.

- **Méthode** :
  - Fournir un mot-clé très long **(par ex., keywords = "Lorem ipsum " * 500).**
  - Vérifier que la fonction lève une **ValueError** avec le message approprié.

**Particularité** Il garantit que la limite de longueur des mots-clés (ligne 26) est respectée.

### 4. test_timeout

- **Objectif** : Vérifier que les erreurs liées à un délai d’attente sont bien gérées.

- **Méthode** :

  - Simuler une exception de délai d'attente en levant manuellement une exception dans le test.
  - Vérifier que le message d'erreur est approprié.

**Particularité**: Bien qu'il ne teste pas directement la gestion des délais dans la fonction **SearchEngine**, ce test vérifie que les exceptions sont correctement propagées et compréhensibles.

# funcSE.py

Le fichier funcSE.py ne fonctionne pas correctement lors de son exécution, car une erreur **HTTP 400: Bad Request** est levée lors de l'appel à l'API Google Custom Search via **urlopen**. 
C'est pour ces raisons que tous les tests pour **ce fichier ont été réalisés avec des mock**, afin de simuler les réponses de l'API sans effectuer de requêtes réelles.

## Différences entre le fichier original et modifié

### Gestion des erreurs dans la fonction Google

- **Lignes ajoutées/modifiées** : 36-42

     ```python
    try:
        response = urlopen(request)
        json_data = json.loads(response.read().decode('utf-8'))

        # Extract the URLs from the response
        links = [item['link'] for item in json_data.get('items', [])]

        if not links:  # Si aucun résultat n'est trouvé
        return URIRef("")  # Retourner un URIRef vide pour indiquer l'absence de résultat

        return URIRef(links[0])
    except Exception as e:
        logger.error(f"Error retrieving results for {keywords}: {e}")
        return URIRef("")  # Retourner un URIRef vide en cas d'erreur

    ```

  - Aucun contrôle si **links** est vide ou si une exception survient.

## Tests unitaires : Explications et choix

### 1. Tests pour la fonction BS4

#### test_bs4_valid_html :

- Vérifie que la fonction **BS4** extrait correctement le texte d’une page HTML valide.
- Simule une réponse HTTP avec une en-tête **Content-Type: text/html** et un contenu HTML.
- **objectif**:
  - Garantit que **BS4** convertit correctement un contenu HTML en texte brut. 

#### test_bs4_non_html_content :

- Vérifie que la fonction **BS4** renvoie un message explicite lorsqu’un contenu non-HTML est rencontré.
- Simule une réponse HTTP avec un **Content-Type** autre que **text/html**.
- **objectif**
  - Assure une gestion propre des pages non-HTML.

#### test_bs4_request_error :

- Simule une erreur de requête HTTP (par exemple, problème de connexion) et vérifie que la fonction renvoie un message d'erreur clair.
- **Objectif**
  - Valide que **BS4** est robuste face aux erreurs réseau.

### 2. Tests pour la fonction Google

#### test_google_valid_response

- Simule une réponse JSON valide avec des liens dans **items**.
- Vérifie que le premier lien est extrait et retourné sous forme de **URIRef**.
  
- **Objectif**:
  - Garantit que la fonction retourne le bon type d'objet (URIRef) en cas de succès.

#### test_google_no_results

- Simule une réponse JSON vide (**items** absent ou vide).
- Vérifie qu’un **URIRef** vide est retourné.
- **objectif**
  - Assure que la fonction gère correctement l'absence de résultats.

#### test_google_request_error

- Simule une erreur HTTP ou autre exception lors de l'appel à l'API.
- Vérifie qu’un URIRef vide est retourné et qu’une erreur est logguée.
- **objectif**
  - Valide que la fonction est robuste face aux erreurs réseau ou API.

# llmgraph_ollama.py

## 1. Différences entre le fichier original et le fichier modifié

### 1.1 Gestion des URI invalides

- Ligne modifiée : **44-46**

    ```python
    if not isinstance(uri, URIRef) or not is_valid_uri(uri):
        logger.debug(f"Invalid URI: {uri}")
        return URIRef("http://example.org/invalid_uri")
    ```

- **Utilité** 
  - Vérifie si l'argument **uri** est bien une instance de **URIRef** et si elle est valide.
  - Retourne une URI par défaut (**http://example.org/invalid_uri**) en cas d’URI non valide, évitant des erreurs lors du traitement.

### 1.2 Gestion des erreurs d'appel à l'API OLLAMA

- Lignes ajoutées : 54-68 :

  ```python
    try:
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()

        if response.status_code == 200:
            result = response.json()
            jsonld_data = result.get("response", "")
        else:
            named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                            Literal(f"API Error: {response.status_code}", datatype=XSD.string)))
            return graph_uri

    except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error: {e}")
            named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                            Literal("Timeout Error", datatype=XSD.string)))
            raise

    except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            named_graph.add((URIRef(uri), URIRef("http://example.org/has_error"),
                            Literal(f"Request Error: {str(e)}", datatype=XSD.string)))
            return graph_uri

    ```

- **Utilité** :
  - Gère différents types d’erreurs réseau (**Timeout, RequestException**).
  - Ajoute un triplet au **named_graph** en cas d’erreur pour consigner la nature du problème.
  - Si l'API retourne un code d’erreur HTTP, consigne l’erreur et retourne le **graph_uri**.

### 1.3 Gestion des erreurs liées au JSON-LD

- **Ligne ajoutée/modifiée : 71**

```python
jsonld_data = result.get("response", "")
```

- **Utilité** :

  - Utilise **.get()** pour extraire de manière sécurisée la clé "**response**" dans le JSON retourné. Si la clé n’existe pas, retourne une chaîne vide, évitant ainsi des erreurs.

- Lignes supprimées/redondantes : 82-86

  ```python
    response = requests.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    ```

  - Ces lignes ont été supprimées pour éviter un double appel à l'API OLLAMA.
  
## 2. Explication des tests unitaires

### Test avec une URI invalide 

- **Fonction** : Vérifie que les URI invalides sont correctement identifiées et renvoient **http://example.org/invalid_uri.**

- **Approche** :
  - Fournit une URI non valide (**"not_a_valid_uri"**).
  - Vérifie que le résultat est bien **http://example.org/invalid_uri**.


### Test des erreurs réseau (timeout et autres exceptions)


- **Fonction** : Simule des erreurs de réseau pour vérifier la robustesse de la fonction.
- **Approche** :
  - Utilise un **mock** pour simuler des erreurs comme **Timeout** ou **RequestException**.
  - Vérifie que le triplet d’erreur est bien ajouté au **named_graph**.

### Test avec un résultat JSON-LD valide :

- **Fonction** : Vérifie que les données JSON-LD sont correctement parsées et ajoutées au graphe RDF.
- **Approche**
  - Simule une réponse API avec un contenu JSON-LD valide.
  - Vérifie que le graphe nommé contient les triplets attendus.

### Test avec un résultat JSON-LD invalide

- **Fonction** : Valide la gestion des erreurs lorsque le JSON retourné n’est pas correctement formé.
- **Approche** :
  - Simule une réponse JSON malformée.
  - Vérifie qu’un triplet d’erreur est ajouté au graphe.
  
### Test de l’absence de résultat dans le JSON-LD

- **Fonction** : Vérifie que la fonction gère correctement un résultat API vide.
- **Approche** :
  - Fournit une réponse JSON sans clé "**response**".
  - Vérifie que la fonction ne tente pas de parser le JSON-LD.

### Test avec un prompt vide 

- **Fonction** : Vérifie que la fonction lève une erreur lorsque le prompt est vide.
- **Approche** :
  - Fournit un prompt vide.
  - Vérifie qu’une exception est levée.


### Test avec un modèle ou une URL non définis

- **Fonction** : Vérifie que la fonction détecte l’absence de configuration (model ou api_url).
- **Approche** :
  - Modifie temporairement la configuration pour supprimer ces valeurs.
  - Vérifie que des assertions échouent.

# llmgraph.py

## 1. Différences entre le fichier original et le fichier modifié

## 1.1 Ajout d'un paramètre response_override

- Ligne ajoutée : 19

```python
  def LLMGRAPH(prompt, uri, response_override=None):
```

- **Utilité** :
  - Le paramètre **response_override** permet de fournir une réponse simulée directement au lieu d'appeler l'API OpenAI.
  - Très utile pour les tests unitaires, car cela évite les appels externes tout en permettant de tester la logique interne.

### 1.2 Gestion des URI invalides

- **Ligne modifiée : 25**

```python
if not isinstance(uri, URIRef):
    raise ValueError("LLMGRAPH 2nd Argument should be an URI")
```

- **Utilité** :
  - Vérifie que l'argument uri est une instance valide de URIRef.
  - Empêche l'exécution avec des URI mal formées, améliorant la robustesse.

### 1.3 Gestion des réponses RDF

- **Lignes modifiées : 28-34**

```python
if response_override:
    response_content = response_override
else:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0
    )
    response_content = response.choices[0].message.content
```

- **Utilité** :

  - Permet de passer une réponse simulée (**response_override**) au lieu d’appeler l’API OpenAI.
  - Réduit la dépendance aux services externes, particulièrement utile en phase de tests.

### 1.4 Changement du format de parsing

- **Ligne modifiée : 43**
  
```python
named_graph.parse(data=rdf_data, format="turtle")
```

- **Utilité** :

  - Dans le fichier original, le format JSON-LD était utilisé pour parser les réponses.
  - Le format Turtle est désormais utilisé, car il est plus adapté au contenu RDF généré par certains prompts.

## 2. Explication des tests unitaires

### Test avec un contenu Turtle valide

- **Fonction** :
  - Vérifie que la réponse RDF au format Turtle est correctement parsée et ajoutée au graphe RDF.
- **Approche** :
  - Fournit une réponse Turtle simulée contenant des informations sur une personne.
  - Vérifie que les triplets RDF, notamment le type **schema:Person**, sont bien ajoutés.

### Test avec une URI invalide

- **Fonction** :
  - Vérifie que la fonction lève une erreur en cas d'URI mal formée.
- **Approche** :
  - Fournit une URI sous forme de chaîne non conforme ("**invalid_uri**").
  - Vérifie qu’une **ValueError** est levée.


### Test avec une réponse RDF mal formée

- **Fonction** :
  - Vérifie la robustesse face à des réponses RDF Turtle incorrectes.
- **Approche** :
  - Fournit une réponse Turtle mal formée (par exemple, une URI non fermée).
  - Vérifie que la fonction lève une **ValueError** avec un message d’erreur pertinent.

### Test avec une réponse RDF vide

- **Fonction** :
  Vérifie que la fonction gère les réponses vides correctement.
- **Approche** :
  - Fournit une réponse simulée vide.
  - Vérifie qu’une ValueError est levée pour signaler l’absence de contenu à parser.

### Test de l’ajout des triplets au graphe nommé

- **Fonction** :
  Vérifie que les triplets extraits sont bien ajoutés au graphe RDF nommé.
- **Approche** :
  - Utilise un contenu RDF valide et simule l’ajout au graphe.
  - Parcourt les triplets pour vérifier leur exactitude.

# readdir.py

Le fichier readdir.py ne fonctionne pas lorsqu'il est exécuté, générant l'erreur suivante :
**TypeError: 'NoneType' object is not subscriptable.**

Cela est probablement dû à une erreur dans le traitement des variables ou à l'absence de gestion adéquate pour des cas particuliers (comme un répertoire vide ou inexistant). Par conséquent, les tests ont été effectués exclusivement à l'aide de mocks pour simuler les comportements attendus, sans exécuter directement les fonctions du fichier original

## 1. Différences entre le fichier original et le fichier modifié

### 1.1 Simplification de la fonction principale

- **Fichier original**
  - La fonction principale **RDIR** effectue une liste complexe de tâches, incluant la gestion des graphes RDF et des chemins locaux, mais cette logique est étroitement couplée avec **os** et les fonctions de gestion des fichiers.

- **Fichier modifié**
  - La version modifiée remplace cette complexité par une fonction distincte appelée **readhtmlfile** :

```python
def readhtmlfile(path_uri, max_size):
```

- **Objectif** :
  - La nouvelle version simplifie le traitement en isolant la lecture des fichiers HTML locaux.
  - Elle tronque le contenu textuel à **max_size** et retourne un objet **Literal**.

### 1.2 Vérification des erreurs de lecture

- **Fichier original**
  - Dans le fichier original, les erreurs liées aux chemins ou fichiers inexistants ne sont pas explicitement gérées.

- **Fichier modifié**
  - Des gestionnaires d'erreurs clairs sont ajoutés :

```python
except FileNotFoundError:
    logger.error(f"File not found: {path_uri}")
    return Literal(f"Error reading {path_uri}")
except OSError as e:
    logger.error(f"OS error: {e}")
    return Literal(f"Error reading {path_uri}")
```

- **Utilité** :
  - Ces blocs permettent de capturer et de signaler les erreurs liées à l'accès aux fichiers.

### 1.3 Changement des responsabilités

- Fichier original
  - La fonction **RDIR** manipule à la fois les graphes RDF et les chemins locaux.

- Fichier modifié
  - La version simplifiée utilise la fonction **readhtmlfile** pour se concentrer sur la lecture et le traitement des fichiers HTML :

```python
uri_text = h.handle(data).strip()
uri_text_uni = unidecode.unidecode(uri_text).strip()
```

- **Utilité :**
  - Réduit les responsabilités de la fonction principale en déléguant le traitement HTML à **html2text**.

### 1.4 Ajout de journaux détaillés

Des journaux plus détaillés ont été ajoutés pour tracer les erreurs et les résultats :
```python
logger.debug(f"result={uri_text_uni[:max_size]}")
```

- **Utilité :**
  - Facilite le débogage et la compréhension des erreurs.

## 2. Choix des tests unitaires

**Structure des tests**
Les tests utilisent des patches pour remplacer les fonctions critiques :

```python
@patch('SPARQLLM.udf.readdir.list_directory_content', return_value=["file1.txt", "file2.txt"])
@patch('SPARQLLM.udf.readdir.add_triples_to_graph')
```

**Objectif** :
Simuler le comportement des fonctions et s'assurer qu'elles interagissent correctement.

### 2.1 Test avec un répertoire valide

- **Fonction :**
  - Vérifie que la fonction traite correctement un répertoire contenant des fichiers.
- **Approche :**
  - Simule un répertoire contenant deux fichiers (**file1.txt** et **file2.txt**) à l'aide de **mock_listdir**.
  - Vérifie que les triplets RDF générés contiennent les chemins et métadonnées des fichiers.
  
### 2.2 Test avec un graphe existant

- **Fonction :**
  - Vérifie que la fonction ne régénère pas un graphe si celui-ci existe déjà.
- **Approche :**
  - Simule un graphe nommé existant via **mock_named_graph_exists**.
  - Vérifie que la fonction retourne None dans ce cas.
  
### 2.3 Test avec un répertoire vide

- **Fonction** :
  - Vérifie que la fonction gère correctement les répertoires vides.
- **Approche** :
  - Simule un répertoire sans contenu à l'aide de **mock_listdir**.
  - Vérifie que le graphe RDF généré est vide.

# readfile.py 

## 1. Différences entre le fichier original et le fichier modifié

### 1.1 Vérification et normalisation des résultats

Dans le fichier original, le contenu extrait avec **html2text** est directement utilisé :

```python
uri_text = h.handle(data)
uri_text_uni = unidecode.unidecode(uri_text).strip()
```

Dans le fichier modifié, une étape supplémentaire est ajoutée pour normaliser le texte extrait en supprimant les caractères inutiles comme les hashtags (#) ou les espaces en début de ligne :

```python
uri_text = h.handle(data).strip()
uri_text = uri_text.lstrip("# ").strip()
uri_text_uni = unidecode.unidecode(uri_text).strip()
```

**Utilité :**
Cette étape améliore la qualité du texte en supprimant les artefacts HTML résiduels et en normalisant le formatage.

### 1.2 Gestion des erreurs détaillée

Dans le fichier original, seules les erreurs liées à **requests.exceptions.RequestException** sont capturées :

```python
except requests.exceptions.RequestException as e:
    return Literal("Error reading {uri}")
```

Dans le fichier modifié, une gestion plus fine des erreurs est introduite pour capturer des exceptions comme **FileNotFoundError et OSError :**

```python
except FileNotFoundError:
    logger.error(f"File not found: {path_uri}")
    return Literal(f"Error reading {path_uri}")
except OSError as e:
    logger.error(f"OS error: {e}")
    return Literal(f"Error reading {path_uri}")
```

**Utilité :**
Ces modifications offrent des messages d'erreur plus précis et permettent de tracer les erreurs dans les journaux.

## 2. Explications des choix de tests et approche

### Test 1 : Fichier HTML valide

- **But :**
  - Vérifier que la fonction extrait correctement le contenu d'un fichier HTML valide et le tronque si nécessaire.
- **Approche :**
  - Utilisation de **mock_open** pour simuler un fichier HTML contenant du texte structuré.
  - Vérification que le texte est correctement extrait et tronqué.

### Test 2 : Taille maximale dépassée

- **But** :
  - Vérifier que le contenu est tronqué si sa taille dépasse **max_size**.
- **Approche** :
  - Simulation d'un fichier contenant un texte long.
  - Vérification que la longueur du texte retourné ne dépasse pas **max_size**.

### Test 3 : Fichier introuvable

- **But** :
  - Vérifier que la fonction retourne un message d'erreur clair si le fichier est inexistant.
- **Approche** :
  - Simulation d'une exception **FileNotFoundError** à l'aide de **patch**.
  - Vérification que le résultat contient un message indiquant l'erreur.

### Test 4 : Fichier non HTML

- **But :**
  - Vérifier que la fonction gère les fichiers contenant du texte brut.
- **Approche :**
  - Simulation d'un fichier contenant du texte brut.
  - Vérification que le texte brut est correctement retourné.

### Test 5 : Fichier HTML vide

- **But** :
  - Vérifier que la fonction retourne une chaîne vide pour un fichier HTML vide.
- **Approche** :
  - Simulation d'un fichier HTML vide.
  - Vérification que le résultat est une chaîne vide.

### Test 6 : Caractères spéciaux

- **But** :
  - Vérifier que les caractères spéciaux sont correctement convertis.
- **Approche** :
  - Simulation d'un fichier contenant des caractères spéciaux.
  - Vérification que les caractères spéciaux sont normalisés.

# recurse.py

Le fichier **recurse.py** ne fonctionne pas correctement en raison de l'erreur suivante :
Error retrieving **file:///Users/molli-p/SPARQLLM** does not look like a valid URI, trying to serialize this will break.

Cela signifie que le chemin d'entrée **(file:///Users/molli-p/SPARQLLM)** n'est pas traité comme un URI valide. Cette erreur peut être liée à un problème de manipulation ou de conversion de l'URI dans le code ou à une mauvaise configuration d'environnement.

## 1. Différences entre le fichier original et modifié

nous n'avons pas eu ç faire des modifications pour le fichier recurse.py

## 2. Explication des tests

### Test 1 : Fonctionnement normal

- **But** : 
  - Vérifier que la fonction gère correctement une requête SPARQL avec des résultats valides.
- **Approche** :
  - Simuler une requête retournant plusieurs résultats **(gout)**.
  - Vérifier que la fonction retourne l'URI du graphe final attendu.

### Test 2 : Graphe nommé déjà existant

- **But** : 
  - Vérifier que la fonction retourne **None** si le graphe nommé existe déjà.
- **Approche** :
  - Simuler que le graphe nommé existe (**named_graph_exists** retourne **True**).
  - Vérifier que la fonction ne crée pas de nouveau graphe.

### Test 3 : Dépassement de la profondeur maximale

- **But** : 
  - Vérifier que la fonction s’arrête à la profondeur maximale.
- **Approche** :
  - Simuler une requête avec des résultats (**gout**).
  - Limiter **max_depth** à **0** et vérifier que la récursion ne continue pas.
  
### Test 4 : Gestion des exceptions

- **But** : 
  - Vérifier que la fonction capture correctement les exceptions.
- **Approche** :
  - Simuler une exception levée par la requête SPARQL.
  - Vérifier que l’URI final est toujours retourné malgré l’erreur.

### Test 5 : Test de la fonction testrec

- **But** : 
  - Vérifier que testrec exécute correctement une requête avec des résultats valides.
- **Approche** :
  - Simuler une réponse SPARQL avec des valeurs spécifiques (**max_s**).
  - Vérifier que les valeurs sont affichées correctement.

# schemaorg.py

## 1. Différences entre le fichier original et le fichier modifié

### 1. Ajout de la fonction is_valid_turtle

- **Lignes ajoutées : 16-30** (dans le fichier modifié)
- Code ajouté :
```python
def is_valid_turtle(turtle_data):
    """
    Vérifie si une chaîne de caractères est un RDF Turtle bien formé.
    Args:
        turtle_data (str): Chaîne à vérifier.

    Returns:
        bool: `True` si le Turtle est valide, `False` sinon.
    """
    if not turtle_data.strip():
        logger.error("Empty Turtle data is not valid.")
        return False

    graph = Graph()
    try:
        graph.parse(data=turtle_data, format="turtle")
        return True
    except Exception as e:
        logger.error(f"Invalid Turtle data: {e}")
        return False
```

- **Utilité** :
  - Permet de valider les données RDF Turtle avant de les parser.
  - Empêche les erreurs inattendues lors de la tentative de parsing de données mal formées ou vides.
  - Fournit une vérification explicite pour améliorer la robustesse de la fonction **SCHEMAORG**.

### 2. Modification de la fonction SCHEMAORG

- **Lignes modifiées : 35-37, 58-61, 75-79**(dans le fichier modifié).
- Code modifié :
**Vérification du store**

```python
if rdf_store is None:
    global store
    rdf_store = store
```

- **Utilité :**
  - Évite l'utilisation non contrôlée de la variable globale **store** en permettant de fournir un store RDF personnalisé (utile pour les tests).

**Validation et parsing des données Turtle**

```python
if is_valid_turtle(response_text):
    try:
        named_graph.parse(data=response_text, format="turtle")
        logger.debug("Valid Turtle data added to graph.")
    except Exception as e:
        logger.error(f"Error parsing Turtle data: {e}")
        raise ValueError(f"Error processing RDF data: {e}")
```

- **Utilité** :
  - S'assure que seules les données Turtle valides sont ajoutées au graphe RDF.
  - Fournit une gestion claire des erreurs si les données sont mal formées.

### 3. Suppression de l'ancien global store

- **Ligne supprimée : 21** (dans le fichier original).

```python
global store
```

- **Utilité** :
  - Réduit la dépendance aux variables globales, ce qui rend le code plus modulaire et testable.

## 2. Choix des fonctions pour les tests et explications

### Approche pour les tests

- **Données simulées** :

  - Des chaînes de caractères représentant des données RDF Turtle valides, mal formées ou vides sont utilisées.
  - Permet un contrôle total sur les cas de test sans dépendre d'une connexion réseau.

- **Utilisation d'assertions explicites :**

  - Utilisation de assertRaises pour vérifier que des exceptions sont levées dans les cas appropriés.
  - Utilisation de assertTrue et assertFalse pour tester les fonctions de validation.

- **Isolation des tests :**

  - Chaque test est indépendant et ne dépend pas de l'état modifié par un autre test.
  - Le store RDF (rdf_store) est réinitialisé au besoin pour garantir un environnement propre.

### 1. Tests pour la fonction SCHEMAORG

- **test_invalid_uri** :

  - Vérifie si une URI invalide déclenche une exception.
  - Utilité : Assure la validation correcte des URI dès le début.

- **test_valid_turtle** :

  - Teste le parsing correct des données RDF Turtle valides.
  - Utilité : Vérifie que la fonction ajoute correctement des triplets RDF valides au graphe nommé.

- **test_malformed_turtle** :

  - Teste le comportement avec une URI invalide à la place des données mal formées.
  - Utilité : Confirme que la fonction gère correctement les URI non valides sans tenter de les parser.

- **test_empty_response** :

  - Teste le comportement avec une réponse vide.
  - Utilité : Vérifie que la fonction gère les réponses sans contenu de manière appropriée.

### 2. Tests pour la fonction is_valid_turtle

- **test_is_valid_turtle_with_valid_data** :

  - Vérifie si la fonction reconnaît des données RDF Turtle valides.
  - Utilité : Confirme que la validation fonctionne pour des données correctement formées.

- **test_is_valid_turtle_with_invalid_data** :

  - Vérifie si la fonction détecte les erreurs dans des données mal formées.
  - Utilité : Assure que les données invalides ne passent pas la validation.

- **test_is_valid_turtle_with_empty_data** :

  - Teste le comportement avec une chaîne vide.
  - Utilité : Vérifie que les chaînes vides ne sont pas considérées comme valides.

# segraph_scrap.py

## 1. Différences entre le fichier original et le fichier modifié

### 1. Ajout du paramètre response_override dans SEGRAPH_scrap

- **Lignes modifiées : 43, 55-58** (fichier modifié).
- Code ajouté/modifié :

```python
def SEGRAPH_scrap(keywords, link_to, nb_results=5, response_override=None):
```

```python
if response_override is not None:
    links = response_override
else:
    engine = Google()
    results = engine.search(keywords, pages=1)
    links = results.links()
```

- **Utilité** :
  - Le paramètre **response_override** permet de fournir des résultats simulés pour les tests.
  - Cela évite de faire appel à un moteur de recherche externe pendant les tests.
  - Rend la fonction plus testable et indépendante des appels réseau réels.
  
### 2. Validation des mots-clés (keywords)

- **Lignes ajoutées : 48-49** (fichier modifié).
- Code ajouté :

```python
if not keywords.strip():
    raise ValueError("Invalid keywords: keywords cannot be empty or whitespace")
```

- **Utilité** :
  - Empêche la recherche avec des mots-clés vides ou constitués uniquement d'espaces.
  - Garantit une validation claire des entrées avant d'exécuter la logique principale.

### 3. Vérification et utilisation du graphe RDF global store

- **Lignes modifiées : 42-43** (fichier modifié).
- Code modifié :

```python
global store
```

- **Utilité** :
  - Maintient la compatibilité avec le **store** global tout en permettant une gestion explicite dans les tests.

### 4. Simplification de la gestion des liens

- **Lignes modifiées : 58-65** (fichier modifié).
- Code modifié :

```python
for item in links[:nb_results]:
    logger.debug(f"SEGRAPH_scrap found: {item}")
    named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(item)))
```

- **Utilité** :
  - Ajoute les liens trouvés directement au graphe RDF, tout en limitant le nombre de résultats à **nb_results**.

### 5. Gestion explicite des erreurs

- **Lignes modifiées : 65-67** (fichier modifié).
- Code ajouté :

```python
except Exception as e:
    logger.error(f"SEGRAPH_scrap: Error during search: {e}")

```

- **Utilité** :
  - Permet de capturer et de consigner les erreurs de recherche pour faciliter le débogage.

## 2. Choix des fonctions pour les tests et explications

### Approche pour les tests

- **Données simulées** :

  - Les tests utilisent des listes simulées de liens (**valid_links, empty_links**).
  - Cela élimine les dépendances vis-à-vis des appels réseau réels.

- **Validation des exceptions :**

  - Utilisation de assertRaises pour vérifier que des exceptions sont levées dans les cas invalides.
  - Exemple :
  
  ```python
  with self.assertRaises(ValueError) as context:
      SEGRAPH_scrap(keywords, link_to)
  ```

- **Vérification du contenu du graphe :**

  - Les tests valident les triplets RDF ajoutés au graphe nommé.
  - Exemple :

  ```python
  self.assertTrue((link_to, URIRef("http://example.org/has_uri"), URIRef(link)) in named_graph)
  ```

- **Isolation des tests** :

  - La méthode setUp nettoie le graphe avant chaque test :

  ```python
  store.remove((None, None, None))
  ```


### test_invalid_link_to

- **fonction** : Vérifie si la fonction déclenche une exception lorsqu'un link_to invalide est fourni.
- **objectif** : Garantir que les entrées non valides sont correctement détectées.

### test_valid_links

- **fonction**: Utilise des liens simulés pour vérifier que la fonction ajoute correctement les résultats au graphe RDF.
- **objectif** : Valider le comportement normal avec des données valides.

### test_empty_links

- **fonction**:Simule une recherche sans résultats pour vérifier que le graphe nommé reste vide.
- **objectif** : : Garantir que la fonction gère correctement les cas où aucun lien n'est trouvé.
  
### test_existing_graph

- **fonction**:Vérifie que la fonction retourne un graphe existant sans le modifier si un graphe correspondant existe déjà.
- **objectif** : Préserver l'intégrité des graphes déjà créés.

### test_nb_results_limit

- **fonction**:Limite le nombre de résultats ajoutés au graphe pour vérifier que la fonction respecte le paramètre **nb_results**.
- **objectif** : S'assurer que la fonction ne traite pas plus de résultats que spécifié.

# segraph.py

Le fichier segraph.py ne fonctionne pas lorsqu'il est exécuté en raison de l'erreur suivante :

```bash
raise HTTPError(req.full_url, code, msg, hdrs, fp)
urllib.error.HTTPError: HTTP Error 400: Bad Request
```

C'est pourquoi tous **les tests** de ce fichier ont été **réalisés uniquement avec des mocks** afin de simuler le comportement attendu et de contourner l'erreur liée aux requêtes HTTP réelles.

## Différences entre le fichier original et le fichier modifié

### 1. Création de fonctions utilitaires

- **Lignes ajoutées : 24-47** dans le fichier modifié
- Code ajouté/modifié :

```python
def validate_arguments(keywords, link_to):
    if not isinstance(link_to, URIRef):
        raise ValueError("SEGRAPH 2nd Argument should be an URI")
    return True

def generate_graph_uri(keywords):
    return URIRef("http://google.com/" + hashlib.sha256(keywords.encode()).hexdigest())

def fetch_links_from_api(se_url, keywords, max_links):
    try:
        full_url = f"{se_url}&q={quote(keywords)}"
        logger.debug(f"Fetching links from URL: {full_url}")
        request = Request(full_url, headers={'Accept': 'application/json'})
        response = urlopen(request)
        json_data = json.loads(response.read().decode('utf-8'))
        return [item['link'] for item in json_data.get('items', [])][:max_links]
    except Exception as e:
        logger.error(f"Erreur réseau ou JSON : {e}")
        raise e

def add_links_to_graph(named_graph, link_to, links):
    for link in links:
        named_graph.add((link_to, URIRef("http://example.org/has_uri"), URIRef(link)))
    logger.debug(f"Graph after adding links: {list(named_graph)}")
    return named_graph
```

- **Utilité :**
  1. **Modularisation** : La logique principale de SEGRAPH a été divisée en fonctions indépendantes pour :

     - Valider les arguments **(validate_arguments)**.
     - Générer l'URI unique d'un graphe basé sur les mots-clés **(generate_graph_uri)**.
     - Récupérer les liens via l'API de recherche (fetch_links_from_api).
     - Ajouter les liens récupérés au graphe RDF **(add_links_to_graph)**.

  2. **Réutilisation** : Chaque fonction peut être testée individuellement, facilitant le débogage et la maintenance.
   
  3. **Lisibilité** : Le code est plus clair et chaque fonction a une responsabilité unique.

### 2. Validation des arguments

- **Lignes modifiées : 50-51** dans le fichier modifié
- Code ajouté :
  
  ```python
  validate_arguments(keywords, link_to)
  ```

- **Utilité :**
  - S'assure que **link_to** est une URI RDF valide avant de poursuivre l'exécution, en évitant des erreurs en aval.

### 3. Vérification si le graphe existe déjà

- **Lignes modifiées : 52-54** dans le fichier modifié
- Code modifié :

  ```python
  if named_graph_exists(store, graph_uri):
    logger.debug(f"Graph {graph_uri} already exists (good)")
    return graph_uri
  ```

- **Utilité** :
  - Si un graphe correspondant aux mots-clés existe déjà, il est immédiatement retourné, évitant des appels inutiles à l'API et améliorant les performances.

### 4. Appel à l'API et gestion des erreurs

- **Lignes modifiées : 55-58** dans le fichier modifié
- Code modifié :

```python
links = fetch_links_from_api(se_url, keywords, max_links)
```

- **Utilité** :
  - Centralise l'appel à l'API et la gestion des erreurs dans la fonction **fetch_links_from_api**, rendant **SEGRAPH** plus lisible.

### 5. Ajout des liens au graphe RDF

- **Lignes modifiées : 59-60** dans le fichier modifié
- Code modifié :

```python
add_links_to_graph(named_graph, link_to, links)
```

- **Utilité** :
  - Délègue la responsabilité d'ajouter les liens au graphe à une fonction dédiée, ce qui simplifie la fonction principale.

## Choix des fonctions pour les tests et méthodologie

### test_validate_arguments

- Vérifie si la validation des arguments (**keywords, link_to**) fonctionne correctement.
- Cas testés :
  
  1. Entrées valides.
  2. Entrées invalides.

### test_generate_graph_uri

Vérifie que l'URI généré pour un graphe correspond bien au **hash SHA-256 des mots-clés.**

### test_fetch_links_from_api

Simule une réponse JSON contenant des liens et vérifie que seuls les liens spécifiés sont extraits.

### test_add_links_to_graph

Vérifie que les liens fournis sont correctement ajoutés au graphe RDF.

### test_segraph_with_results

Simule une recherche renvoyant plusieurs liens et vérifie que les liens sont correctement ajoutés au graphe.

### test_segraph_no_results

Simule une recherche sans résultats et vérifie que le graphe reste vide.

### test_segraph_with_existing_graph

Vérifie que si un graphe existant est détecté, il est simplement retourné sans être modifié.

### test_segraph_invalid_link_to

Vérifie que la fonction lève une exception si **link_to** n'est pas une URI valide.

### test_segraph_http_error

Simule une erreur réseau (ex. : API non disponible) et vérifie que l'exception est correctement levée.

# SPARQLLM.py

## Introduction

Pour ce fichier, **il était impossible de réaliser les tests sans mocks** pour les raisons suivantes :
1. **Complexité des dépendances :** Les fonctions comme **evalGraph**, **evalServiceQuery** et **evalLazyJoin** dépendent directement de la manière dont **rdflib** gère les requêtes SPARQL dans un contexte dynamique. Tester ces appels directement aurait nécessité de réorganiser l'ensemble du projet pour simuler un environnement SPARQL complet.
2. **Store dynamique** : La création dynamique des graphes dans le **store** repose sur des comportements qui émergent pendant l'exécution des requêtes SPARQL. Cela aurait nécessité de configurer un environnement RDF complexe.
3. **Efforts de maintenance** : Réorganiser tout le projet pour tester directement ce fichier aurait non seulement pris beaucoup de temps, mais aurait également compliqué la maintenance future.

C'est pourquoi **tous les tests ont été réalisés à l'aide de mocks**, qui permettent de simuler les appels et de vérifier les comportements sans exécuter réellement les opérations sous-jacentes.

## Choix des fonctions pour les tests et méthodologie

### 1. my_evaljoin

- **Objectif du test** :

  - Vérifier que la fonction appelle correctement evalLazyJoin et retourne son résultat.

- **Méthodologie** :

  - Utilisation de **unittest.mock.patch** pour remplacer **evalLazyJoin** par un mock.
  - Simuler une réponse "**lazyJoinResult**" de la part de **evalLazyJoin**.
  - Vérifier que :
    - La fonction **evalLazyJoin** est appelée une seule fois avec les bons arguments (**ctx, part**).
    - Le résultat retourné par **my_evaljoin** correspond à "**lazyJoinResult**".

### 2. my_evalgraph

- **Objectif du test** :

  - Vérifier que la fonction appelle correctement **evalGraph** et retourne son résultat.
  
- **Méthodologie** :
  - Mock de **evalGraph** pour simuler une réponse "**graphResult**".
  - Vérifier que :
    - **evalGraph** est appelé une seule fois avec les bons arguments.
    - Le résultat retourné par **my_evalgraph** est "**graphResult**".
  
### 3. my_evalservice

- **Objectif du test :**

  - Vérifier que la fonction appelle correctement **evalServiceQuery** et retourne son résultat.

- **Méthodologie** :

  - Mock de **evalServiceQuery** pour simuler une réponse "**serviceQueryResult**".
  - Vérifier que :
    - **evalServiceQuery** est appelé une seule fois avec les bons arguments.
    - Le résultat retourné par **my_evalservice** est "**serviceQueryResult**". 

### 4. customEval

#### a) Cas pour Join

- **Objectif du test**:

  - Vérifier que customEval appelle correctement my_evaljoin lorsque **part.name == "Join"**.
- **Méthodologie** :
  - Configuration de **part.name** pour qu'il retourne "**Join**".
  - Mock de **evalLazyJoin** pour simuler une réponse "**customJoinResult**". 
  - Vérifier que :
    - **evalLazyJoin** est appelé avec les bons arguments.
    - **customEval** retourne "**customJoinResult**".

#### b) Cas non supporté

- **Objectif du test** :

  - Vérifier que **customEval** lève une exception **NotImplementedError** pour les **part.name** non supportés.
- **Méthodologie** :
  - Configuration de **part.name** avec une valeur non implémentée.
  - Utilisation de **assertRaises** pour vérifier que l'exception est levée.

### 5. Initialisation et création dynamique du store

#### a) Initialisation

- **Objectif du test** :

  - Vérifier que le **store** est bien un **Dataset** initialement vide.

- **Méthodologie** :

  - Mock de **Dataset** pour vérifier son initialisation.
  - Vérifier que le **store** est vide à sa création.

#### b) Création dynamique

- **Objectif du test** :
  - Vérifier que des graphes peuvent être créés dynamiquement dans le **store**. 
- **Méthodologie** :
  - Ajout d'un triplet à un graphe dans le **store**.
  - Vérification que le graphe contient le triplet. 

# uri2text.py

## 1. Différences entre le fichier original et le fichier modifié

###  1. Nettoyage des caractères Markdown

- **Code original** (Ligne 27):

  ```python
  uri_text_uni = unidecode.unidecode(uri_text).strip()
  ```

- **Code modifié** (Lignes 31-32) :
  
  ```python
  uri_text_cleaned = unidecode.unidecode(uri_text).strip()
  uri_text_cleaned = uri_text_cleaned.lstrip("#").strip()
  ```

- **Utilité** : Supprime les caractères de type Markdown (#, etc.) en début de texte pour rendre la sortie plus propre.

### 2. Ajout de la gestion des liens

- **Code original** : Aucun réglage spécifique pour ignorer les liens dans le contenu HTML transformé.

- **Code modifié** (Ligne 30) :

```python
h.ignore_links = True
```

- **Utilité** : Ignore les liens dans le contenu transformé en texte pour éviter d'avoir des URL inutiles dans la sortie.

### 3. Vérification de Content-Type

- Code original (Ligne 20):

  ```python
  if 'text/html' in response.headers['Content-Type']:
  ```

- Code modifié (Ligne 24):

  ```python
  if 'text/html' in response.headers.get('Content-Type', ''):
  ```

- **Utilité** : Utilisation de **.get()** pour éviter une erreur potentielle si l'en-tête **Content-Type** est absent.

### 4. Ajout d'un message d'erreur amélioré

- **Code original** (Ligne 23):
  
  ```python
  return Literal("No HTML content at {uri}")
  ```
- **Code modifié** (Ligne 35) :
  
  ```python
  return Literal(f"No HTML content at {uri}", datatype=XSD.string)
  ```

- **Utilité** : Fournit un message plus clair et utilise explicitement le type **XSD.string.**

### 5. Logging amélioré pour les erreurs

- **Code original** (Ligne 26) :
  
  ```python
  return Literal("Error retreiving {uri}")
  ```
  
- **Code modifié** (Lignes 37-38):
  
  ```python
  logger.error(f"Error retrieving {uri}: {e}")
  return Literal(f"Error retrieving {uri}", datatype=XSD.string)
  ```

- **Utilité** : Ajout d’un journal détaillé pour les erreurs, afin de faciliter le débogage.

## 2. Explication des choix de fonctions pour les tests

### Méthodologie pour les tests

- **Utilisation d’un serveur HTTP local** :

  - Un serveur HTTP local est créé dans **setUpClass** pour simuler différentes réponses (HTML valide, JSON, erreurs, etc.).
  - Cela permet de tester la fonction sans dépendre de ressources externes.

- **Tests exhaustifs** :

- Les tests couvrent tous les cas possibles :
  - Contenu HTML valide.
  - Contenu non HTML.
  - Réponse trop longue.
  - Timeout.
  - Erreurs HTTP.
  - URI invalide.
  
- **Isolation** :

  - Chaque test est indépendant des autres grâce au serveur HTTP local simulé.
  - Cela garantit que les résultats d’un test n’affectent pas les autres.

### 1. test_valid_html

- **Objectif** : Vérifie que la fonction traite correctement une URI renvoyant un contenu HTML valide.
  
- **Méthode** :
  - Simulation d’un serveur renvoyant un HTML simple : **\<h1>Hello, world!\</h1>.**
  - Vérification que le texte extrait est **"Hello, world!"** et qu’il est encapsulé dans un **Literal**.

### 2. test_non_html_content

- **Objectif** : Vérifie que la fonction renvoie un message d’erreur pour un contenu non HTML.

- **Méthode** :
  - Simulation d’une URI renvoyant un **Content-Type** JSON.
  - Vérification que le message renvoyé est **No HTML content at {uri}**.

### 3. test_large_response

- **Objectif** : Vérifie que la fonction tronque correctement un contenu dépassant la taille maximale (**max_size**).

- **Méthode** :
  - Simulation d’une réponse très longue (**10 000 caractères**).
  - Vérification que la sortie est tronquée à **max_size** caractères.

### 4. test_timeout

- **Objectif** : Vérifie que la fonction gère les erreurs de timeout.
  
- **Méthode** :
Simulation d’une erreur **HTTP 408 (Request Timeout)**.
Vérification que le message renvoyé est **Error retrieving {uri}**.

### 5. test_http_error

- **Objectif** : Vérifie que la fonction gère les erreurs **HTTP (ex. : erreur 500)**.
- **Méthode** :
  - Simulation d’une erreur **HTTP 500 (Internal Server Error)**.
  - Vérification que le message renvoyé est **Error retrieving {uri}**.

### 6. test_invalid_uri

- **Objectif** : Vérifie que la fonction gère correctement une URI invalide.
- **Méthode** :
  - Utilisation d'une URI malformée (**not-a-valid-uri**).
  - Vérification que le message renvoyé est **Error retrieving {uri}**.