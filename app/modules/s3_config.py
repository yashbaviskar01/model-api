import boto3
from botocore.exceptions import NoCredentialsError
import os
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

S3_SCHEMA_BUCKET_NAME = os.getenv("S3_SCHEMA_BUCKET_NAME")

def get_s3_client() -> boto3.client:
    """
    Returns a boto3 S3 client with credentials and region from environment variables.
    """
    try:
        # Client to test locally
        # s3_client = boto3.Session(profile_name='YASH').client('s3')

        s3_client = boto3.client('s3')
        return s3_client
    except NoCredentialsError:
        logger.error("AWS credentials not found.")
        raise
    except Exception as e:
        logger.error(f"Error initializing S3 client: {e}")
        raise


def upload_to_s3(content: str, object_key: str) -> None:
    """
    Uploads a string content directly to an S3 bucket.
    """
    try:
        s3_client = get_s3_client()
        s3_client.put_object(Body=content, Bucket=S3_SCHEMA_BUCKET_NAME, Key=object_key)
        logger.info(f"File uploaded successfully to {S3_SCHEMA_BUCKET_NAME}/{object_key}.")
    except Exception as e:
        logger.error(f"Error uploading content to S3: {e}")
        raise
    

def fetch_table_metadata_from_s3(table_name: str) -> str:
    """
    Fetch the metadata (DDL) from an S3 bucket for the given table name.
    """
    try:
        s3_client = get_s3_client()
        object_key = f"agentplatform/{table_name}.md"
        response = s3_client.get_object(Bucket=S3_SCHEMA_BUCKET_NAME, Key=object_key)
        content = response['Body'].read().decode('utf-8')
        logger.info(f"Metadata file for table {table_name} fetched successfully.")
        return content
    except Exception as e:
        logger.error(f"Error fetching metadata for table {table_name}: {e}")
        raise
