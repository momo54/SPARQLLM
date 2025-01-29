import os
import faiss
import nltk

nltk.download('averaged_perceptron_tagger_eng')
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredHTMLLoader
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore


embeddings = OllamaEmbeddings(
    model="jina/jina-embeddings-v2-small-en"
)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)



def chunk_docs():
    folder_path = "./Pset/pset_length"
    htmls = []
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.endswith(".html"):
                htmls.append(os.path.join(root, filename))
    #print(len(htmls))
    docs = []
    for html in htmls:
        try:
            loader = UnstructuredHTMLLoader(html, encoding='utf8')
            docs.extend(loader.load())
        except Exception as e:
            print(f"Error processing file {html}: {e}")
    #print(docs)
    return docs

def get_embeddings():
    docs = chunk_docs()
    chunks = text_splitter.split_documents(docs)
    #print(len(chunks))
    #print(chunks[3].page_content)

    ##Type of Vector Store
    single_vector = embeddings.embed_query(chunks[0].page_content)
    index = faiss.IndexFlatL2(len(single_vector))
    vector_store = FAISS(
        embedding_function=embeddings,
        index=index,
        docstore=InMemoryDocstore(),
        index_to_docstore_id={}
    )
    db_name = "pset_vector_store"

    ##Create the vector store and add the documents from the chunks
    ids = vector_store.add_documents(documents=docs)
    vector_store.save_local(db_name)
    #print(vector_store)
    #print(vector_store.index_to_docstore_id)
    ##Load the local vector store if existing
    #new_vector = FAISS.load_local(db_name, embeddings=embeddings, allow_dangerous_deserialization=True)
    #print(len(new_vector.index_to_docstore_id))


if __name__ == "__main__":
    get_embeddings()