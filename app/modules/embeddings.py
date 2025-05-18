import os
from dotenv import load_dotenv
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_openai import OpenAIEmbeddings
from opensearchpy import OpenSearch, OpenSearchException, RequestsHttpConnection
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
 
load_dotenv()
 
class handle_embeddings:
    def __init__(self):
        self.index_name = "agent-platform-coda-service"
        self.embedding_model = OpenAIEmbeddings(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("EMBEDDING_MODEL")
        )
        self.vectorstore = self.get_vectorstore()
        self.client = OpenSearch(
            hosts=os.getenv("CLUSTER_URL"),
            http_auth=(os.getenv("USERNAME"),os.getenv("PASSWORD")),
            verify_certs=True,
            timeout=60,
            max_retries=3,
            retry_on_timeout=True,
            connection_class=RequestsHttpConnection
        )
 
    def get_vectorstore(self):
        try:
            return OpenSearchVectorSearch(
                embedding_function=self.embedding_model,
                index_name=self.index_name,
                http_auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")),
                use_ssl=True,
                verify_certs=True,
                ssl_assert_hostname=False,
                ssl_show_warn=False,
                opensearch_url=os.getenv("CLUSTER_URL"),
                text_field="page_content",
                metadata_field="metadata",
                vector_field="vector_field",
                search_type="painless_scripting",
                timeout=60,
                retry_on_timeout=True,
                max_retries=3
            )
        except OpenSearchException as e:
            print(f"Error creating vectorstore: {str(e)}")
            return None
   
    def create_index_body(self, index_name):
        try:
            # Check if index exists
            if self.client.indices.exists(index=index_name):
                print(f"Index '{index_name}' already exists!")
                return True
       
            index_body = {
                'settings': {
                    "index.knn": True,
                    "number_of_shards": 1,
                    "number_of_replicas": 1
                },
                "mappings": {
                    "properties": {
                        "vector_field": {
                            "type": "knn_vector",
                            "dimension": 1536,  
                            "method": {
                                "engine": "faiss",
                                "name": "hnsw",
                                "space_type": "l2"
                            }
                        }
                    }
                }
            }
            response = self.client.indices.create(index=index_name, body=index_body)
            print(f"Index '{index_name}' created successfully!")
            return response
        except OpenSearchException as e:
            print(f"Error creating index: {str(e)}")
            return False
 
 
    def chunk_documents_txt(self, docs, chunk_size=1024, chunk_overlap=50):
            """Splits Markdown documents into smaller chunks while preserving structure."""
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap
            )
           
            chunked_docs = []
            for doc in docs:
                if isinstance(doc, Document):
                    chunks = text_splitter.split_text(doc.page_content)
                    chunked_docs.extend([Document(page_content=chunk) for chunk in chunks])
                else: 
                    chunks = text_splitter.split_text(doc.get("page_content", ""))
                    chunked_docs.extend([{"page_content": chunk} for chunk in chunks])
           
            print(f"Chunked {len(docs)} TXT documents into {len(chunked_docs)} smaller chunks.")
            return chunked_docs
 
 
    def embedding_docs(self, vectorstore, docs, batch_size=50):
            """Embeds Markdown documents after chunking."""
            chunked_docs = self.chunk_documents_txt(docs)
            total_docs = len(chunked_docs)
            successful_embeddings = 0
 
            for i in range(0, total_docs, batch_size):
                batch = chunked_docs[i : i + batch_size]
                try:
                    vectorstore.add_documents(documents=batch)
                    successful_embeddings += len(batch)
                    print(f"Progress: {successful_embeddings}/{total_docs} chunks embedded")
                except OpenSearchException as e:
                    print(f"Error embedding batch {i//batch_size + 1}: {str(e)}")
 
            return successful_embeddings