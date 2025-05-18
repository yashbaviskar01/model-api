import os
import textwrap
from dotenv import load_dotenv
from loguru import logger
import openai  # Import the OpenAI package for embeddings
from openai import OpenAI  # Used for the OpenRouter client
from app.modules.s3_config import upload_to_s3

load_dotenv()

# ------------------------ Configuration ------------------------
# Define the model and token limit for OpenRouter (Google Gemini model)

TABLE_DESCRIPTION_MODEL = os.getenv('TABLE_DESCRIPTION_MODEL')

MODEL_MAX_TOKENS = 8192

# Define the OpenAI embedding model
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL')

# Configure the API keys (ensure these are set in your .env file)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Set the OpenAI API key for the embeddings call
openai.api_key = OPENAI_API_KEY

# ------------------------ GENERATE TABLE DESCRIPTION ------------------------

def generate_table_description(result, table_name: str):
    """
    Generate detailed table and column descriptions using OpenAI model (GPT-4O-MINI).

    Accepts a list of dictionaries as input (result).
    """
    db_name = "agentplatform"  # Hardcode the database name here

    try:
        # Extract columns from the result
        columns = list(result[0].keys())

        # Convert the first few rows of data to a string format
        rows = result[:5]  # Take the first 5 rows as an example
        rows_str = "\n".join([str(row) for row in rows])

        prompt = textwrap.dedent(f"""
        You are a senior database architect with expertise in SQL DDL generation. Based on the provided table name, column names, and sample data, generate a precise SQL DDL statement.

        ### Requirements:
        - Generate a `CREATE EXTERNAL TABLE` statement for `{table_name}`
        - Each column must include an appropriate SQL data type
        - Include `COMMENT` annotations for each column based on inferred meaning
        - Define a `PRIMARY KEY` if an identifier column exists
        - Use consistent formatting for readability
        - Include additional annotations for `Tags`, `Purpose`, and `Description` at the end of the DDL

        ### Output Format:
        ```
        CREATE EXTERNAL TABLE {table_name} (
            column_name1 DATA_TYPE COMMENT 'Description',
            column_name2 DATA_TYPE COMMENT 'Description',
            ...
            column_nameN DATA_TYPE COMMENT 'Description',
            CONSTRAINT pk_{table_name} PRIMARY KEY (primary_key_column)
        );

        Tags: tag1, tag2, tag3;
        Purpose: Description of the table's purpose;
        Description: More detailed explanation of the table's role and use case;
        ```

        ### Data for Analysis:
        - Table Name: {table_name}
        - Columns: {', '.join(columns)}

        Sample data (first 5 rows):
        {rows_str}

        Ensure the SQL DDL is production-ready, well-commented, and includes the required tags, purpose, and description sections.
        """)

        logger.info("Sending prompt to OpenAI gpt-4o-mini model for detailed table description generation.")

        # Invoke the model with the constructed prompt using the OpenAI client
        response = openai.chat.completions.create(
            model=TABLE_DESCRIPTION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.02,
            max_tokens=MODEL_MAX_TOKENS,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )

        # Extract the response content
        description = response.choices[0].message.content

        # Clean up the SQL formatting markers if present
        description = description.replace("```sql", "").replace("```", "")

        logger.info("Received response from OpenAI model.")

        # Upload the response content directly to S3
        object_key = f"{db_name}/{table_name}.md"
        upload_to_s3(description, object_key)

        return description

    except Exception as e:
        logger.error(f"Error invoking OpenAI model or uploading file to S3: {e}")
        return "Error generating description from OpenAI model."


def generate_embedding(text: str):
    """
    Given text, returns the embedding using the OpenAI API (text-embedding-3-small model).
    """
    try:
        response = openai.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        # Extract the embedding from the response
        embedding = response.data[0].embedding
        logger.info("Embedding generated successfully using OpenAI.")
        return embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        raise
