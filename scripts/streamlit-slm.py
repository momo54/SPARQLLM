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
# import SPARQLLM.udf.SPARQLLM as sparqllm
from SPARQLLM.udf.SPARQLLM import store, reset_store
from SPARQLLM.utils.utils import print_result_as_table


# Logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("SPARQLLM.udf")
logger.setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# 🏗️ Load the Knowledge Graph with RDFLib
st.title("🔎 SPARQL-LM (SLM)")

st.write("Combining Knowledge Graph, Search Engines, and LLM in a single SPARQL query.")

# Need a config file
CONFIG = "./config.ini" 

if "config_singleton" not in st.session_state:
    st.session_state.config_singleton = ConfigSingleton(config_file=CONFIG)

# Retrieve the singleton
config_instance = st.session_state.config_singleton


# Directory containing SPARQL queries
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


# Initialize query state if it does not exist
if "query_text" not in st.session_state:
    st.session_state.query_text = default_query

# Update the query when a new file is selected
if query_content != st.session_state.query_text:
    st.session_state.query_text = query_content


# Display the query text area with secure updates
query = st.text_area("📝 Enter your SPARQL query:", height=200, key="query_text")

# 🎯 Execute the SPARQL query
if st.button("Execute Query"):
    reset_store()
    try:
        assert store is not None, "store is None"
        assert len(list(store.contexts())) == 1, "store is not empty"
        results = store.query(query)

        # Convert results to DataFrame
        data = []
        for row in results:
            data.append([str(value) for value in row])
        
        df = pd.DataFrame(data, columns=[str(var) for var in results.vars])
        st.write("### 🔍 Query Results:")
        st.dataframe(df)

        st.write(f"### Named Graphs")

        # #----------------
        named_graphs = list(store.contexts())

        if not named_graphs:
            st.warning("⚠️ No named graphs found in the dataset.")
        else:
            # Create a table of named graphs
            data = [{"Graph": str(c.identifier), "Triples": len(c)} for c in named_graphs]
            df = pd.DataFrame(data)

            # Display the table
            st.write("### 📊 Named Graphs and Their Content")
            st.dataframe(df)

            for selected_graph_obj in named_graphs:
                for s, p, o in selected_graph_obj:
                    print(f"Subject: {s}, Predicate: {p}, Object: {o}")  # Debugging
                triples = [{"Subject": str(s), "Predicate": str(p), "Object": str(o)} 
                           for s, p, o in selected_graph_obj]

                if triples:
                    df_triples = pd.DataFrame(triples)
                    st.write(f"### 📜 Triples of Named Graph `{selected_graph_obj.identifier}`")
                    st.dataframe(df_triples, use_container_width=True)
                    st.json(triples, expanded=False)

                else:
                    st.info(f"ℹ️ The named graph `{selected_graph_obj.identifier}` contains no triples.")
        # #----------------
        

    except Exception as e:
        st.error(f"Error executing the query: {e}")

# Display the log...
st.title("Logs")

# Placeholder for logs
log_placeholder = st.empty()

# Function to display logs with auto-scroll in HTML/JS
def update_logs():
#    logs_html = "<div id='log-container' style='height:300px; overflow-y:auto; padding:10px; background-color:#f8f9fa; border-radius:5px;'>"
    logs_html = "<div id='log-container' style='height:300px; overflow-y:auto; padding:10px; border-radius:5px;'>"
    logs_html += "<br>".join(st.session_state.log_messages)
    logs_html += "</div>"
    log_placeholder.markdown(logs_html, unsafe_allow_html=True)

def extract_function_name(logger_name):
    match = re.search(r'\.udf\.(\w+)', logger_name)
    return match.group(1) if match else "Unknown"

# Function to capture and display logs
class StreamlitHandler(logging.Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        log_entry = self.format(record)

        function_name = extract_function_name(record.name)
        formatted_entry = f"[{function_name}] {log_entry[:60]}"

        st.session_state.log_messages.append(formatted_entry)
        
        # Limit the number of displayed logs to avoid excessive memory usage
        if len(st.session_state.log_messages) > 1000:
            st.session_state.log_messages = st.session_state.log_messages[-1000:]

        update_logs() 

        # Update the log area with a scrollbar
        # log_placeholder.text_area("Logs", "\n".join(st.session_state.log_messages), height=300)


for handler in logger.handlers[:]:  # Copy the list to avoid removal errors
    logger.removeHandler(handler)

handler = StreamlitHandler()
logger.addHandler(handler)

# Disable log propagation to avoid duplicates
logger.propagate = False

if "log_messages" not in st.session_state:
    st.session_state.log_messages = []
