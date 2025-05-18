import re
from app.schemas.schema import ChatState
from app.utils.s3_prompts_config import get_prompt
import app.utils as utils
import datetime

class WorkflowNodes:
    def __init__(
        self,
        client,
        opensearch_client,
        text_to_sql_model: str,
        final_answer_model: str,
        run_athena_query,
        wait_for_query_to_complete,
        get_query_results,
        generate_embedding,
        logger,
    ):
        self.client = client
        self.opensearch_client = opensearch_client
        self.text_to_sql_model = text_to_sql_model
        self.final_answer_model = final_answer_model
        self.run_athena_query = run_athena_query
        self.wait_for_query_to_complete = wait_for_query_to_complete
        self.get_query_results = get_query_results
        self.generate_embedding = generate_embedding
        self.logger = logger

    async def process_user_query(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: process_user_query")
        self.logger.info(f"Processing user query: {state.query}")
        # (Business logic can be added here)
        self.logger.info(f"State just before return in process_user_query: {state.model_dump()}")
        self.logger.info("Exiting function: process_user_query")
        return state

    async def similarity_search(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: similarity_search")
        self.logger.info("Generating embedding and performing cosine similarity search on OpenSearch.")
        try:
            embedding = self.generate_embedding(state.query)
            top_k = 5
            search_body = {
                "size": top_k,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": embedding,
                            "k": top_k
                        }
                    }
                }
            }
            response = self.opensearch_client.search(index="data_service_index", body=search_body)
            similar_tables = []
            for hit in response["hits"]["hits"]:
                similar_tables.append({
                    "table_name": hit["_source"]["table_name"],
                    "description": hit["_source"]["table_description"],
                    "score": hit["_score"]
                })
            state.similar_tables = similar_tables
            self.logger.info(f"Found similar tables: {similar_tables}")
        except Exception as e:
            self.logger.error(f"Error during similarity search: {e}")
            state.similar_tables = []
    
        self.logger.info(f"State just before return in similarity_search: {state.model_dump()}")
        self.logger.info("Exiting function: similarity_search")
        return state

    async def generate_sql_query(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: generate_sql_query")
        self.logger.info("Generating SQL query using OpenAI.")
        try:
            if state.similar_tables:
                combined_schema = "\n".join(
                    [f"Table: {t['table_name']}\nDescription: {t['description']}" for t in state.similar_tables]
                )
            else:
                combined_schema = "No relevant table schema available."
        
            member_filter = f"id = '{state.uuid}'" if state.uuid else "/* id filter missing */"

            # add today's date
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            self.logger.info(f"Today's date: {today_date}")
            
            prompt_template = get_prompt('generate_sql_query')
            # Format the template with the necessary dynamic values.
            prompt = prompt_template.format(
                combined_schema=combined_schema,
                query=state.query,
                member_filter=member_filter,
                today_date=today_date
            )

            self.logger.info(f"SQL PROMPT:==================>> \n\n{prompt}")
            response = self.client.chat.completions.create(
                model=self.text_to_sql_model,
                messages=[{"role": "user", "content": prompt}]
            )
            sql_query = response.choices[0].message.content
            sql_query = sql_query.replace("```sql", "").replace("```", "")
            state.sql_query = sql_query
            self.logger.info(f"Generated SQL query: {sql_query}")
        except Exception as e:
            self.logger.error(f"Error generating SQL query: {e}")
            state.sql_query = ""
        
        self.logger.info(f"State just before return in generate_sql_query: {state.model_dump()}")
        self.logger.info("Exiting function: generate_sql_query")
        return state

    async def execute_sql_query(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: execute_sql_query")
        self.logger.info("Executing SQL query on Athena using existing athena_client logic.")
        try:
            if state.sql_query:
                query_execution_id = self.run_athena_query(state.sql_query)
                state_result = self.wait_for_query_to_complete(query_execution_id)
                if state_result != 'SUCCEEDED':
                    self.logger.error(f"Query did not succeed: {state_result}")
                    state.sql_result = f"Query failed with state: {state_result}"
                else:
                    result = self.get_query_results(query_execution_id)
                    
                    # Attempt to extract the deeplink from the SQL result.
                    try:
                        if isinstance(result, list) and result:
                            # Extract the deeplink from the first row if available
                            first_row = result[0]
                            deeplink_val = first_row.get("deeplink")
                            state.deeplink = deeplink_val if deeplink_val is not None else None
                        else:
                            state.deeplink = None
                        
                        # Remove the 'deeplink' key from all rows to avoid passing it to final answer generation.
                        if isinstance(result, list):
                            for row in result:
                                if "deeplink" in row:
                                    del row["deeplink"]
                    except Exception as deeplink_error:
                        self.logger.error(f"Error extracting deeplink: {deeplink_error}")
                        state.deeplink = None
                        
                    state.sql_result = result
                self.logger.info(f"SQL execution result: {state.sql_result}")
            else:
                self.logger.error("No SQL query to execute.")
                state.sql_result = ""
        except Exception as e:
            self.logger.error(f"Error executing SQL query: {e}")
            state.sql_result = ""
        
        self.logger.info(f"State just before return in execute_sql_query: {state.model_dump()}")
        self.logger.info("Exiting function: execute_sql_query")
        return state

    async def fetch_table_prompt(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: fetch_table_prompt")
        self.logger.info("Fetching table prompt from s3 bucket.")
        try:
            table_name = None
            if state.sql_query:
                match = re.search(r"FROM\s+([^\s;]+)", state.sql_query, re.IGNORECASE)
                if match:
                    table_name = match.group(1)
                    self.logger.info(f"Extracted table name from SQL query: {table_name}")
                    # Store the table name in the state
                    state.table_used = table_name
            
            if table_name:
                prompt = get_prompt(table_name)
                if not prompt:
                    self.logger.error(f"No prompt found in S3 for table '{table_name}'. Using default prompt.")
                    prompt = "Default table prompt"
            else:
                prompt = "Default table prompt"
            
            if isinstance(prompt, list):
                prompt = "\n".join(prompt)
            
            state.table_prompt = prompt
            self.logger.info(f"Fetched table prompt: {state.table_prompt}")
        except Exception as e:
            self.logger.error(f"Error fetching table prompt: {e}")
            state.table_prompt = ""
    
        self.logger.info(f"State before return in fetch_table_prompt: {state.model_dump()}")
        self.logger.info("Exiting function: fetch_table_prompt")
        return state

    async def generate_final_answer(self, state: ChatState) -> ChatState:
        self.logger.info("Entering function: generate_final_answer")
        self.logger.info("Generating final answer using LangGraph flow.")
        try:
            prompt_template = get_prompt('generate_final_answer')
            # Format the prompt template with dynamic state values.
            prompt = prompt_template.format(
                query=state.query,
                sql_query=state.sql_query,
                sql_result=state.sql_result,
                table_prompt=state.table_prompt
            )
    
            response = self.client.chat.completions.create(
                model=self.final_answer_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.02
            )
            final_answer = response.choices[0].message.content
            final_answer = final_answer.replace("```", "")
            state.final_answer = final_answer
            self.logger.info(f"Final answer generated: {final_answer}")
        except Exception as e:
            self.logger.error(f"Error generating final answer: {e}")
            state.final_answer = "Error generating final answer."
        
        self.logger.info(f"State just before return in generate_final_answer: {state.model_dump()}")
        self.logger.info("Exiting function: generate_final_answer")
        return state

    async def answer_directly_with_rag(self, state: ChatState) -> ChatState:
        """
        New node to handle general/RAG queries. It bypasses the SQL flow and
        directly generates an answer using the RAG fusion technique.
        """
        self.logger.info("Entering function: answer_directly_with_rag")
        try:
            from app.modules.rag import GenerateChat
            rag_generator = GenerateChat()
            answer = rag_generator.answer_question_with_rag_fusion(state.query)
            state.final_answer = answer
            self.logger.info("Generated answer using RAG fusion.")
        except Exception as e:
            self.logger.error(f"Error in answer_directly_with_rag: {e}")
            state.final_answer = "Error generating answer with RAG fusion."
        self.logger.info(f"State just before return in answer_directly_with_rag: {state.model_dump()}")
        self.logger.info("Exiting function: answer_directly_with_rag")
        return state