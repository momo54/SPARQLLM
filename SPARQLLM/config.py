import configparser
import logging
import importlib
from rdflib.plugins.sparql.operators import register_custom_function, unregister_custom_function
from rdflib import URIRef
import json


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
    _models = {}

    def __new__(cls,config_file='config.ini'):
        logger = logging.getLogger(__name__)

        if cls._instance is None:
            cls._instance = super(ConfigSingleton, cls).__new__(cls)
            cls._instance.config = configparser.ConfigParser()
            cls._instance.config.optionxform = str  # Preserve case sensitivity for option names
            logger.debug(f"Reading {config_file} for configuration")
            cls._instance.config.read(config_file)

            config=cls._instance.config

            for section in config.sections():
                if section.startswith('Models.'):
                    # Extraire le nom du modèle (par exemple, 'SLM-OLLAMA3' ou 'SLM-OLLAMA4')
                    model_name = section.replace('Models.', '')
                    
                    # Extraire le model (format JSON) et l'URL depuis la section
                    payload = json.loads(config.get(section, 'payload'))  # Convertir la chaîne JSON en dictionnaire
                    url = config.get(section, 'url')
                    key_prompt = config.get(section, 'key_prompt')
                    timeout = config.get(section, 'timeout')
                    key_reponse = config.get(section, 'key_reponse')
                    
                    # Ajouter au dictionnaire sous la forme souhaitée
                    cls._models[model_name] = {
                        "payload": payload,
                        "url": url,
                        "key_prompt": key_prompt,
                        "timeout": timeout,
                        "key_reponse": key_reponse
                    }

            associations = config['Associations']
            registered_functions = {}

            for uri, full_func_name in associations.items():
                module_name, func_name = full_func_name.rsplit('.', 1)
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
                if callable(func):
                    full_uri = f"http://example.org/{uri}"
                    logger.debug(f"Registering {func_name} with URI {full_uri}")
                    register_custom_function(URIRef(full_uri), func)
                    registered_functions[uri] = func
                else:
                    logger.error(f"Initialization: Function {func_name} is NOT callable.")

            # Process Extensions
            if 'Extensions' in config.sections():
                extensions = config['Extensions']
                
                for uri, full_func_name in extensions.items():
                    module_name, func_name = full_func_name.rsplit('.', 1)
                    module = importlib.import_module(module_name)
                    extension_func = getattr(module, func_name)
                    # Encapsulate the original function with the extension
                    if callable(extension_func) and uri in registered_functions:
                        # Encapsulate the original function
                        original_func = registered_functions[uri]

                        def create_wrapped_func(original, extension):
                            def wrapped(*args, **kwargs):
                                # Appelle uniquement l'extension sans passer 'original' comme argument
                                return extension(original, *args, **kwargs)
                            return wrapped

                        # Create the wrapped function
                        wrapped_func = create_wrapped_func(original_func, extension_func)
                        logger.debug(f"Encapsulating {uri} with {func_name}")
                        full_uri = f"http://example.org/{uri}"

                        # Unregister and re-register with the wrapped function
                        unregister_custom_function(URIRef(full_uri))
                        register_custom_function(URIRef(full_uri), wrapped_func)
                    else:
                        logger.error(f"Initialization: Extension {func_name} for {uri} is NOT callable.")


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