import os
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
import logging
logger = logging.getLogger(__name__)

embeddings = OllamaEmbeddings(
    model="jina/jina-embeddings-v2-small-en"
)
db_name = "pset_vector_store"
def retrieval_se(query, nb_result=5):
    files = os.listdir("pset_vector_store")
    to_string_files = str(files)
    logger.debug(f"Query: {query}")
    n = int(nb_result)
    ##Load the local vector store if existing
    vector_store = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    #chunks = vector_store.similarity_search(query=query,k=n)
    retriever = vector_store.as_retriever(search_type="mmr",
                                          search_kwargs={'k': n,
                                                        'fetch_k':100,
                                                        'lambda_mult': 1})
    chunks = retriever.invoke(query)
    logger.debug(f"chunks ready")
    result = []
    for chunk in chunks:
        result.append(chunk.page_content)
        print(chunk)
        print("\n\n")
        print("=====================================================================")
        print("\n\n")
    return result

if __name__ == "__main__":
    query = "Abonnement TV"
    retrieval_se(query)