import os
import boto3
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = "exp-dev-agent-platform"
FILE_PATH = r"all_coda_documents.txt"
S3_OBJECT_NAME = "coda_silver_data.txt"

def upload_to_s3():
    try:
        s3_client = boto3.client("s3")
        s3_client.upload_file(FILE_PATH, BUCKET_NAME, S3_OBJECT_NAME)
        print(f"File uploaded successfully to s3://{BUCKET_NAME}/{S3_OBJECT_NAME}")
    except Exception as e:
        print(f"Error uploading file: {e}")
upload_to_s3()
