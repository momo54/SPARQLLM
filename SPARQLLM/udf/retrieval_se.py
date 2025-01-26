from re import search

from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
import logging
logger = logging.getLogger(__name__)

embeddings = OllamaEmbeddings(
    model="jina/jina-embeddings-v2-small-en"
)
db_name = "pset_vector_store"
def retrieval_se(query, k=5):

    logger.debug(f"Query: {query}")
    ##Load the local vector store if existing
    vector_store = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    #chunks = vector_store.search(query,search_type="similarity")
    retriever = vector_store.as_retriever(search_type="mmr",
                                          search_kwargs={'k': k,
                                                        'fetch_k':100,
                                                        'lambda_mult': 1})
    chunks = retriever.invoke(query)
    result = []
    for chunk in chunks:
        result.append(chunk.page_content)

    logger.debug(f"Result: {len(result)}")
    print(result)
    return result

if __name__ == "__main__":
    query = "Abonnement TV"
    retrieval_se(query)