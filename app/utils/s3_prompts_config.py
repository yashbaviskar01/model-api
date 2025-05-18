import os
import logging
import boto3

# S3 bucket name is expected to be set as an environment variable.
S3_PROMPT_BUCKET_NAME = os.getenv("S3_PROMPT_BUCKET_NAME")

# s3_client = boto3.Session(profile_name='YASH').client('s3')

s3_client = boto3.client("s3")

def get_prompt(prompt_name: str) -> str:
    """
    Fetches the content of the specified prompt from S3.
    The object key is constructed as '{prompt_name}.txt'.
    Returns the prompt content if found; otherwise, returns an empty string.
    """
    key = f"{prompt_name}.md"
    try:
        response = s3_client.get_object(Bucket=S3_PROMPT_BUCKET_NAME, Key=key)
        content = response["Body"].read().decode("utf-8")
        return content
    except Exception as e:
        logging.error(f"Error fetching prompt '{prompt_name}' from S3: {e}")
        return ""

def update_prompt(prompt_name: str, content: str) -> bool:
    """
    Updates or uploads the prompt content to S3.
    The object key is constructed as '{prompt_name}.txt'.
    Returns True on success; otherwise, returns False.
    """
    key = f"{prompt_name}.md"
    try:
        s3_client.put_object(Bucket=S3_PROMPT_BUCKET_NAME, Key=key, Body=content)
        return True
    except Exception as e:
        logging.error(f"Error updating prompt '{prompt_name}' in S3: {e}")
        return False
