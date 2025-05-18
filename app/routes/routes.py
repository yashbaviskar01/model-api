import os
import json
import boto3
from fastapi import APIRouter, HTTPException
from app.modules.fetch import S3FileHandler
from app.utils.llm import generate_embedding
from app.modules.s3_config import fetch_table_metadata_from_s3
from app.modules.opensearch_database import store_table_embedding_to_opensearch
from app.schemas.schema import QuestionRequest, QuestionResponse, TableReq, TableResp, ChatRequest, ChatResponse
from app.modules.rag import GenerateChat
from app.utils.conversation_summary import generate_conversation_summary
from app.utils.utility_functions import Utils
from app.utils.athena_client import get_table_data
from app.utils.llm import generate_table_description
from app.langgraph.chat_flow import ChatWorkflow
from loguru import logger
 
router = APIRouter()
 
__version__ = "1.0.2"
 
@router.get("/")
async def home() -> dict:
    return {"health_check": "OK", "version": __version__}

@router.post("/inject_bronze_to_silver")
async def inject_data():
    try:
        inject = S3FileHandler()
        return inject.process_all_pdfs()
    except Exception as e:
        logger.error(f"Error in inject_data: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/create_knowledge_base_from_s3")
def create_knowledge_base():
    inject = None  # Predefine inject, so it's available in finally
    try:
        inject = S3FileHandler()
        result = inject.process_s3_data()
        
        # Only delete files if the embedding creation was successful
        if result.get("status") == "success":
            try:
                # Delete from silver-layer
                inject.delete_s3_prefix(os.environ.get("SILVER_BUCKET_NAME"), os.environ.get("SILVER_FILE"))
                # Delete from bronze-layer
                inject.delete_s3_prefix(os.environ.get("BRONZE_BUCKET_NAME"), os.environ.get("BRONZE_FILE"))
                logger.info("Successfully deleted files after successful embedding creation")
            except Exception as delete_error:
                logger.error(f"Error deleting S3 objects: {delete_error}")
        else:
            logger.warning(f"Embedding creation failed, not deleting source files: {result.get('message')}")
            
        return result
    except Exception as e:
        logger.error(f"Error in create_knowledge_base: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/query_knowledge_base", response_model=QuestionResponse)
async def query_rag(request: QuestionRequest):
    try:
        result =GenerateChat().answer_question_with_rag_fusion({"question": request.question})
        return QuestionResponse(answer=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate_table_description", response_model=TableResp)
async def generate_description(request: TableReq) -> TableResp:
    try:
        results = get_table_data(request.table_name)
        logger.info(f"Results: {results}")
        description = generate_table_description(results, request.table_name)
        return TableResp(description=description)
    except Exception as e:
        logger.error(f"Error generating description for table {request.table_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/store_table_embedding", response_model=TableResp)
async def store_table_embedding(request: TableReq) -> TableResp:
    """
    Fetches table metadata from S3, generates embeddings, and stores the data in OpenSearch.
    """
    try:
        # Step 1: Fetch the table metadata from S3
        table_description = fetch_table_metadata_from_s3(request.table_name)
        logger.info(f"Table Description: {table_description}")
        
        # Step 2: Generate embeddings for the DDL
        embedding = generate_embedding(table_description)
        logger.info(f"Table embedding: {embedding}")
        
        # Step 3: Store the table metadata and embedding in OpenSearch
        store_table_embedding_to_opensearch(request.table_name, table_description, embedding)
        
        return TableResp(description=f"Table {request.table_name} Description and embedding stored successfully.")
    
    except Exception as e:
        logger.error(f"Error processing table {request.table_name}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        conversation_summary = ""
        # If this is the first message, generate a concise conversation summary using the utility function
        if request.is_first_message:
            conversation_summary = generate_conversation_summary(request.question)
        
        # Initialize ChatWorkflow and execute the main chat process
        chat_workflow = ChatWorkflow()
        final_state = await chat_workflow.run(query=request.question, uuid=request.uuid)
        
        if final_state.final_answer:
            return ChatResponse(
                answer=final_state.final_answer,
                conversation_summary=conversation_summary,
                deeplink=final_state.deeplink,
                sql_query=final_state.sql_query,
                table_used=final_state.table_used,
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to generate final answer.")
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")