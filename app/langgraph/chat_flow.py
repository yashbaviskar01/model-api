import os
from openai import OpenAI
from dotenv import load_dotenv
from loguru import logger
from langgraph.graph import StateGraph, END

from app.schemas.schema import ChatState
from app.utils.llm import generate_embedding
from app.modules.opensearch_database import opensearch_client
from app.utils.athena_client import run_athena_query, wait_for_query_to_complete, get_query_results

from app.langgraph.data_services_nodes import WorkflowNodes

from app.utils.s3_prompts_config import get_prompt

load_dotenv()

class ChatWorkflow:
    """
    A class that encapsulates the LangGraph chat flow logic.
    Orchestrates the workflow nodes and the state graph.
    """
    def __init__(self, openai_api_key: str = None, text_to_sql_model: str = None, final_answer_model: str = None):
        # Set configuration values via environment variables or provided arguments.
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.text_to_sql_model = text_to_sql_model or os.getenv("TEXT_TO_SQL_MODEL")
        self.final_answer_model = final_answer_model or os.getenv("FINAL_ANSWER_MODEL")
        
        # Initialize shared resources/clients
        self.client = OpenAI(api_key=self.openai_api_key)
    
        # Instantiate the WorkflowNodes with all required dependencies
        self.workflow_nodes = WorkflowNodes(
            client=self.client,
            opensearch_client=opensearch_client,
            text_to_sql_model=self.text_to_sql_model,
            final_answer_model=self.final_answer_model,
            run_athena_query=run_athena_query,
            wait_for_query_to_complete=wait_for_query_to_complete,
            get_query_results=get_query_results,
            generate_embedding=generate_embedding,
            logger=logger
        )
        
        # Build the LangGraph state graph
        logger.info("Building the LangGraph state graph...")
        self.graph = StateGraph(ChatState)
        self.graph.add_node("process_user_query", self.workflow_nodes.process_user_query)
        self.graph.add_node("similarity_search", self.workflow_nodes.similarity_search)
        self.graph.add_node("generate_sql_query", self.workflow_nodes.generate_sql_query)
        self.graph.add_node("execute_sql_query", self.workflow_nodes.execute_sql_query)
        self.graph.add_node("fetch_table_prompt", self.workflow_nodes.fetch_table_prompt)
        self.graph.add_node("generate_final_answer", self.workflow_nodes.generate_final_answer)
        self.graph.add_node("answer_directly_with_rag", self.workflow_nodes.answer_directly_with_rag)  # New RAG node
        
        logger.info("Defining the flow of the graph...")
        self.graph.set_entry_point("process_user_query")
        # Remove direct edge and add conditional routing from process_user_query:
        self.graph.add_conditional_edges(
            "process_user_query",
            self.decide_next_step,  # Conditional function that routes based on query classification
            {
                "database_route": "similarity_search",  # For database queries, continue with similarity search and SQL generation
                "rag_route": "answer_directly_with_rag"   # For general/RAG queries, use the RAG node directly
            }
        )
        # Continue with the existing SQL-based flow
        self.graph.add_edge("similarity_search", "generate_sql_query")
        self.graph.add_edge("generate_sql_query", "execute_sql_query")
        self.graph.add_edge("execute_sql_query", "fetch_table_prompt")
        self.graph.add_edge("fetch_table_prompt", "generate_final_answer")
        # Both final nodes point to END
        self.graph.add_edge("generate_final_answer", END)
        self.graph.add_edge("answer_directly_with_rag", END)
        
        logger.info("Compiling the graph executor...")
        self.executor = self.graph.compile()
    
    async def decide_next_step(self, state: ChatState) -> str:
        """
        Uses the gpt-4o model to classify the user's query into a database query
        or a general/RAG query. Returns the corresponding route.
        """
        # Fetch the prompt template from S3 for classification.
        prompt_template = get_prompt('decide_next_step')

        prompt = prompt_template.format(query=state.query)
        logger.info(f"Decide_next_step:==========> {prompt}")

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-2024-11-20",
                messages=[{"role": "user", "content": prompt}]
            )
            classification = response.choices[0].message.content.strip()
            classification = classification.replace('"', '')

            logger.info(f"Classification of query: ========> {classification}")

            if classification not in ("database_query", "general_query"):
                logger.error(f"Unexpected classification received: {classification}. Defaulting to database_query.")
                classification = "database_query"
        except Exception as e:
            logger.error(f"Error classifying query: {e}. Defaulting to database_query.")
            classification = "database_query"
        
        # Store the classification in the state for future reference.
        state.query_intent = classification
        logger.info(f"Query classified as: {classification}")
        # Map to routing keys used in the conditional edges.
        if classification == "database_query":
            return "database_route"
        else:
            return "rag_route"
    
    async def run(self, query: str, uuid: str = None) -> ChatState:
        """
        Public method to run the entire chat flow.
    
        Args:
            query (str): The user query.
            uuid (str, optional): Optional client UUID.
                
        Returns:
            ChatState: The final state after executing the flow.
        """
        logger.info("Entering method: run")
        logger.info(f"Received query: {query}")
        initial_state = ChatState(query=query, uuid=uuid)
        logger.info("Invoking the executor with the initial state.")
        
        result_dict = await self.executor.ainvoke(initial_state)
        
        if isinstance(result_dict, dict):
            final_state = ChatState(**result_dict)
            logger.info(f"Flow completed successfully. Final state: {final_state.model_dump()}")
        else:
            logger.error("LangGraph did not return a dictionary. Cannot convert to ChatState.")
            raise TypeError("LangGraph did not return a dictionary. Cannot convert to ChatState.")
    
        logger.info("Exiting method: run")
        return final_state
