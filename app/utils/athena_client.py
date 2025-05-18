import os
import time
import boto3
from dotenv import load_dotenv
from loguru import logger

# Load variables from .env file
load_dotenv()

# Validate required environment variables
ATHENA_DATABASE = os.getenv('ATHENA_DATABASE')
ATHENA_OUTPUT_S3_LOCATION = os.getenv('ATHENA_OUTPUT_S3_LOCATION')

# Create a session with your desired profile this is to test locally
# ATHENA_CLIENT = boto3.Session(profile_name='YASH').client('athena')

ATHENA_CLIENT = boto3.client('athena', region_name='us-east-1')


def run_athena_query(query: str):
    """
    Run a query in Athena and return the QueryExecutionId.
    """
    try:
        response = ATHENA_CLIENT.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': ATHENA_DATABASE},
            ResultConfiguration={'OutputLocation': ATHENA_OUTPUT_S3_LOCATION}
        )
        query_execution_id = response['QueryExecutionId']
        logger.info(f"Started Athena query with execution ID: {query_execution_id}")
        return query_execution_id
    except Exception as e:
        logger.exception(f"Error starting Athena query: {e}")
        raise

def wait_for_query_to_complete(query_execution_id: str, sleep_time: int = 2, max_attempts: int = 30):
    """
    Wait for the Athena query to complete.
    Keep while true and sleep time 2 secs
    If state suceed only return the response otherwise print error
    Separate ti states
    """
    attempts = 0
    try:
        while attempts < max_attempts:
            response = ATHENA_CLIENT.get_query_execution(QueryExecutionId=query_execution_id)
            state = response['QueryExecution']['Status']['State']
            logger.info(f"The response of the SQL execution: ==========>> {response}")
            if state in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
                logger.info(f"Query {query_execution_id} finished with state: {state}")
                return state
            time.sleep(sleep_time)
            attempts += 1
    except Exception as e:
        logger.exception(f"Error while waiting for query {query_execution_id} to complete: {e}")
        raise
    raise Exception("Query did not complete in the expected time.")

def get_query_results(query_execution_id: str):
    """
    Retrieve query results from Athena and convert them to a list of dictionaries.
    """
    try:
        result_response = ATHENA_CLIENT.get_query_results(QueryExecutionId=query_execution_id)
        rows = result_response['ResultSet']['Rows']
        if not rows:
            logger.error("No rows returned in query results.")
            return []
        # The first row is assumed to be header with column names
        headers = [col.get('VarCharValue', '') for col in rows[0]['Data']]
        result = []
        for row in rows[1:]:
            data = row.get('Data', [])
            row_dict = {header: col.get('VarCharValue', None) for header, col in zip(headers, data)}
            result.append(row_dict)
        return result
    except Exception as e:
        logger.exception(f"Error fetching query results for execution ID {query_execution_id}: {e}")
        raise

def get_table_data(table_name: str, num_rows: int = 5):
    """
    Get the first few rows of the given table from Athena and return them as a list of dictionaries.
    """
    query = f'SELECT * FROM "{table_name}" LIMIT {num_rows};'
    try:
        query_execution_id = run_athena_query(query)
        state = wait_for_query_to_complete(query_execution_id)
        if state != 'SUCCEEDED':
            raise Exception(f"Query did not succeed, final state: {state}")
        rows = get_query_results(query_execution_id)
        logger.info(f"Fetched {len(rows)} rows from table {table_name}.")
        return rows
    except Exception as e:
        logger.exception(f"Error fetching data from table {table_name}: {e}")
        raise
