import configparser
import logging
import importlib
from rdflib.plugins.sparql.operators import register_custom_function
from rdflib import URIRef

def setup_logger(name=None, level=logging.DEBUG):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

class ConfigSingleton:
    _instance = None

    def __new__(cls,config_file='config.ini'):
        logger = logging.getLogger(__name__)

        if cls._instance is None:
            cls._instance = super(ConfigSingleton, cls).__new__(cls)
            cls._instance.config = configparser.ConfigParser()
            cls._instance.config.optionxform = str  # Preserve case sensitivity for option names
            logger.debug(f"Reading {config_file} for configuration")
            cls._instance.config.read(config_file)

        config=cls._instance.config
        associations = config['Associations']
        for uri, full_func_name in associations.items():
            module_name, func_name = full_func_name.rsplit('.', 1)
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
    #        func = globals().get(func_name)
            if callable(func):
                full_uri= f"http://example.org/{uri}"
                logger.debug(f"Registering {func_name} with URI {full_uri}")
                register_custom_function(URIRef(full_uri), func)
            else:
                logger.error(f"Initialisation : Function {func_name} NOT Collable.")


        return cls._instance
    
    def print_all_values(self):
        """Print all sections, keys, and their values in the config."""
        for section in self.config.sections():
            print(f"[{section}]")
            for key, value in self.config.items(section):
                print(f"{key} = {value}")
            print()  # Blank line between sections

# Provide a function to access the singleton
def get_config():
    return ConfigSingleton().config

# For testing, run with:
#  python -m SPARQLLM.config
if __name__ == "__main__":
    logger = setup_logger(__name__)
    logger.debug("Logger initialisé dans config.py")

#    logging.basicConfig(level=logging.DEBUG)

    # config = ConfigSingleton()
    # print("All configuration values:")
    # config.print_all_values()
    # print(config.config['Associations']['SLM-READDIR'])
    # print(config.config['Requests']['SLM-TIMEOUT'])
    # print(config.config['Requests']['SLM-OLLAMA-MODEL'])

    config = ConfigSingleton(config_file='config-test.ini')
    logging.debug("All configuration values in test:")
    config.print_all_values()
