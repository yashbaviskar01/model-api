import os
import boto3
from dotenv import load_dotenv
from opensearchpy import (
    OpenSearch,
    Urllib3AWSV4SignerAuth,
    Urllib3HttpConnection,
    exceptions as opensearch_exceptions,
)
from loguru import logger

# Load Credentials
load_dotenv()

# ---------- Configuration ----------

# OpenSearch connection settings
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST")
OPENSEARCH_PORT = os.getenv("OPENSEARCH_PORT")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER")
OPENSEARCH_PASS = os.getenv("OPENSEARCH_PASS")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX")


# ---------- Initialize Clients ----------

# Initialize the OpenSearch client with basic authentication (user/password)
opensearch_client = OpenSearch(
    hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
    http_compress=True,
    http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),  # Using user/password authentication
    use_ssl=True,
    verify_certs=True,
    connection_class=Urllib3HttpConnection,
    pool_maxsize=20,
    timeout=300,
)

# Check connection to OpenSearch
try:
    if opensearch_client.ping():
        print("Successfully connected to OpenSearch.")
    else:
        print("Failed to connect to OpenSearch.")
except opensearch_exceptions.OpenSearchException as e:
    print(f"Error connecting to OpenSearch: {e}")


# Create the index with knn_vector field if it doesn't exist
def create_index_if_not_exists(index_name: str, embedding_dimension: int):
    if not isinstance(embedding_dimension, int) or embedding_dimension <= 0:
        raise ValueError(f"Invalid embedding dimension: {embedding_dimension}")

    try:
        if not opensearch_client.indices.exists(index=index_name):
            index_body = {
                "settings": {
                    "index.knn": True,
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "table_name": {"type": "keyword"},
                        "table_description": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": embedding_dimension,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                            }
                        }
                    }
                }
            }
            opensearch_client.indices.create(index=index_name, body=index_body)
            logger.info(f"Index {index_name} created successfully with cosine similarity.")
    except opensearch_exceptions.OpenSearchException as e:
        logger.error(f"Error creating index {index_name}: {e}")
        raise


def store_table_embedding_to_opensearch(table_name: str, table_description: str, embedding: list):
    """
    Stores the table metadata (DDL) and embedding in OpenSearch.
    
    Args:
        table_name (str): Name of the table
        table_description (str): Data Definition Language (DDL) for the table
        embedding (list): Embedding vector for the table
    """
    try:
        # Create the index if it doesn't exist
        embedding_dimension = len(embedding)
        create_index_if_not_exists(OPENSEARCH_INDEX, embedding_dimension)
        
        # Construct the document to be indexed
        document = {
            "table_name": table_name,
            "table_description": table_description,
            "embedding": embedding
        }

        # Check if the table already exists in the index
        search_query = {
            "query": {
                "term": {
                    "table_name": {
                        "value": table_name
                    }
                }
            }
        }
        
        # Perform search to find the document with the same table_name
        response = opensearch_client.search(index=OPENSEARCH_INDEX, body=search_query)
        
        if response['hits']['total']['value'] > 0:
            # If the document exists, update it
            document_id = response['hits']['hits'][0]['_id']
            opensearch_client.update(index=OPENSEARCH_INDEX, id=document_id, body={
                "doc": document
            })
            logger.info(f"Document with table_name {table_name} updated in OpenSearch.")
        else:
            # If the document does not exist, create it
            response = opensearch_client.index(index=OPENSEARCH_INDEX, body=document)
            logger.info(f"Document indexed in OpenSearch with ID: {response['_id']}")

    except opensearch_exceptions.OpenSearchException as e:
        logger.error(f"Error storing or updating embedding in OpenSearch: {e}")
        raise
