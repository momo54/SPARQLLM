import asyncio
import configparser
import io
import logging
import re
import threading
import streamlit as st
import rdflib
import pandas as pd
import networkx as nx
from pyvis.network import Network
import os
import time

import streamlit.components.v1 as components

from SPARQLLM.config import ConfigSingleton
#import SPARQLLM.udf.SPARQLLM as sparqllm
from SPARQLLM.udf.SPARQLLM import store, reset_store
from SPARQLLM.utils.utils import print_result_as_table


# Configuration du logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("SPARQLLM.udf")
logger.setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# 🏗️ Charger le Knowledge Graph avec RDFLib
st.title("🔎 SPARQL-LM (SLM)")

st.write("Combining Knowledge Graph, Search Engines and LLM is a single SPARQL query.")

# need a config file
CONFIG = "./config.ini" 

if "config_singleton" not in st.session_state:
    st.session_state.config_singleton = ConfigSingleton(config_file=CONFIG)

# Récupération du singleton
config_instance = st.session_state.config_singleton


# Directory containing the SPARQL queries
QUERY_DIR = "./queries"

# List files in the directory
if not os.path.exists(QUERY_DIR):
    st.error(f"The directory '{QUERY_DIR}' does not exist.")
    st.stop()

query_files = [f for f in os.listdir(QUERY_DIR) if f.endswith(".sparql")]
default_query = None
if not query_files:
    st.warning("No queries found in the directory.")
    st.stop()
else:
    default_query_path = os.path.join(QUERY_DIR, "city-search.sparql")
    with open(default_query_path, "r", encoding="utf-8") as f:
        default_query = f.read()

# Dropdown to select a query file
selected_query = st.selectbox("Select a query:", query_files)

# Read the content of the selected query file
query_path = os.path.join(QUERY_DIR, selected_query)
with open(query_path, "r", encoding="utf-8") as f:
    query_content = f.read()


# Initialiser l'état de la requête si elle n'existe pas encore
if "query_text" not in st.session_state:
    st.session_state.query_text = default_query

# Mettre à jour la requête lorsque l'utilisateur sélectionne un autre fichier
if query_content != st.session_state.query_text:
    st.session_state.query_text = query_content


# Affichage de la zone de texte avec mise à jour sécurisée
query = st.text_area("📝 Entrez votre requête SPARQL :",  height=200, key="query_text")

# 🎯 Exécution de la requête SPARQL
if st.button("Exécuter la requête"):
    reset_store()
    try:
        assert store is not None, "store is None"
        assert len(list(store.contexts()))==1, "store is not empty"
        results = store.query(query)

        # Transformation en DataFrame
        data = []
        for row in results:
            data.append([str(value) for value in row])
        
        df = pd.DataFrame(data, columns=[str(var) for var in results.vars])
        st.write("### 🔍 Résultats de la requête :")
        st.dataframe(df)

        st.write(f"### named graphs")

        # #----------------
        named_graphs = list(store.contexts())

        if not named_graphs:
            st.warning("⚠️ Aucun graphe nommé trouvé dans le dataset.")
        else:
            # Créer un tableau des graphes nommés
            data = [{"Graphe": str(c.identifier), "Triplets": len(c)} for c in named_graphs]
            df = pd.DataFrame(data)

            # Afficher le tableau
            st.write("### 📊 Graphes nommés et leur contenu")
            st.dataframe(df)

            # Sélectionner un graphe
            # selected_graph = st.selectbox("📌 Sélectionnez un graphe pour voir ses triplets :", 
            #                             [str(c.identifier) for c in named_graphs])

            # Afficher les triplets du graphe sélectionné
            #selected_graph_obj = next((c for c in named_graphs if str(c.identifier) == selected_graph), None)

            for selected_graph_obj in named_graphs:
                for s, p, o in selected_graph_obj:
                    print(f"Sujet: {s}, Prédicat: {p}, Objet: {o}")  # Debugging
                triples = [{"Sujet": str(s), "Prédicat": str(p), "Objet": str(o)} 
                        for s, p, o in selected_graph_obj]

                if triples:
                    df_triples = pd.DataFrame(triples)
                    st.write(f"### 📜 Triplets du graphe `{selected_graph_obj.identifier}`")
                    st.dataframe(df_triples,use_container_width=True)
                    st.json(triples, expanded=False)

                else:
                    st.info(f"ℹ️ Le graphe `{selected_graph_obj.identifier}` ne contient aucun triplet.")
        # #----------------
        


    except Exception as e:
        st.error(f"Erreur lors de l'exécution de la requête : {e}")

# Display the log...
st.title("Logs")

# Espace réservé pour les logs
log_placeholder = st.empty()

# Fonction pour afficher les logs avec auto-scroll en HTML/JS
def update_logs():
#    logs_html = "<div id='log-container' style='height:300px; overflow-y:auto; padding:10px; background-color:#f8f9fa; border-radius:5px;'>"
    logs_html = "<div id='log-container' style='height:300px; overflow-y:auto; padding:10px; border-radius:5px;'>"
    logs_html += "<br>".join(st.session_state.log_messages)
    logs_html += "</div>"
    log_placeholder.markdown(logs_html, unsafe_allow_html=True)

def extract_function_name(logger_name):
    match = re.search(r'\.udf\.(\w+)', logger_name)
    return match.group(1) if match else "Unknown"

# Fonction pour capturer et afficher les logs
class StreamlitHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        log_entry = self.format(record)

        function_name = extract_function_name(record.name)
        formatted_entry = f"[{function_name}] {log_entry[:60]}"

        st.session_state.log_messages.append(formatted_entry)
        
        # Limiter le nombre de logs affichés pour éviter trop de mémoire utilisée
        if len(st.session_state.log_messages) > 1000:
            st.session_state.log_messages = st.session_state.log_messages[-1000:]

        update_logs() 

        # Mettre à jour la zone de logs avec une scrollbar
        # log_placeholder.text_area("Logs", "\n".join(st.session_state.log_messages), height=300)


for handler in logger.handlers[:]:  # Copie de la liste pour éviter les erreurs de suppression
    logger.removeHandler(handler)

handler = StreamlitHandler()
logger.addHandler(handler)

# Désactiver la propagation du logger pour éviter les doublons
logger.propagate = False

if "log_messages" not in st.session_state:
    st.session_state.log_messages = []

