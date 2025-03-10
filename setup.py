from setuptools import setup, find_packages

setup(
    name="SPARQLLM",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        # Liste des dépendances ici, par exemple :
         'rdflib>=7.1.0',   
         'requests>=2.32.3',
         'html2text>=2024.2.26',
            'unidecode>=1.3.8',
        'bs4>=0.0.2',
        'beautifulsoup4>=4.12.3',
        'click>=8.1.7',
        'openai>=1.52.2',
        # Ajoute ici toutes les bibliothèques dont ton projet dépend
    ],
    entry_points={
        'console_scripts': [
            # Si tu as des scripts exécutables, tu peux les déclarer ici
             'slm-explain = SPARQLLM.cli.explain:explain_cmd',
            'slm-run = SPARQLLM.cli.slm:slm_cmd',
            'slm-search-whoosh = SPARQLLM.cli.search_whoosh:search_whoosh',
            'slm-search-faiss = SPARQLLM.cli.search_faiss:search_faiss',
            'slm-index-faiss = SPARQLLM.cli.index_faiss:index_faiss',
            'slm-index-whoosh = SPARQLLM.cli.index_whoosh:index_whoosh',
        ],
    },
    author="Pascal Molli",
    author_email="Pascal.Molli@univ-nantes.fr",
    description="Description de SPARQLLM",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url="https://github.com/momo54/SPARQLLM",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.12',
)
