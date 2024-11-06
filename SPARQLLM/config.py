import configparser
import logging
import importlib
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import URIRef

def configure_udf(config_file):
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case sensitivity for option names
    config.read(config_file)

    # Access the variables by section and key
    slm_timeout = config.getint('Requests', 'SLM-TIMEOUT')        # Read as integer
    slm_ollama_model = config.get('Requests', 'SLM-OLLAMA-MODEL')        # Read as integer 

    associations = config['Associations']
    for uri, full_func_name in associations.items():
        module_name, func_name = full_func_name.rsplit('.', 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
#        func = globals().get(func_name)
        if callable(func):
            full_uri= f"http://example.org/{uri}"
            logging.info(f"Registering {func_name} with URI {full_uri}")
            register_custom_function(URIRef(full_uri), func)
        else:
            logging.error(f"FUnction {func_name} NOT Collable.")




class ConfigSingleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigSingleton, cls).__new__(cls)
            cls._instance.config = configparser.ConfigParser()
            cls._instance.config.read('config.ini')
        return cls._instance

# Provide a function to access the singleton
def get_config():
    return ConfigSingleton().config


# module_a.py
#from config import get_config

#def connect_to_database():
#    config = get_config()
#   host = config['database']['host']