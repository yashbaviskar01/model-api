from pydantic import BaseModel
from typing import List, Optional, Dict,  Any

class QuestionRequest(BaseModel):
    question: str

class QuestionResponse(BaseModel):
    answer: str

class TableReq(BaseModel):
    table_name: str

class TableResp(BaseModel):
    description: str

class ChatRequest(BaseModel):
    question: str
    uuid: Optional[str] = None
    is_first_message: Optional[bool] = False

class ChatResponse(BaseModel):
    answer: str
    conversation_summary: Optional[str] = None
    deeplink: Optional[str] = None  # Added deeplink field
    sql_query: Optional[str] = None
    table_used: Optional[str] = None

class PromptUpdate(BaseModel):
    prompt_name: str
    content: str


# New schema to hold the state for the LangGraph chat flow
class ChatState(BaseModel):
    uuid: Optional[str] = None  # Optional UUID from client if provided
    model_id: Optional[str] = None  # Optional model id if applicable
    query: str
    keywords: List[str] = []
    embedding: Optional[List[float]] = None
    similar_tables: Optional[List[dict]] = None
    sql_query: Optional[str] = None
    sql_result: Optional[List[Dict[str, Any]]] | Optional[str] = None
    table_prompt: Optional[str] = None
    final_answer: Optional[str] = None
    query_intent: Optional[str] = None  # New field to store the classification ("database_query" or "general_query")
    attempts: int = 0
    deeplink: Optional[str] = None  # Added deeplink field
    table_used: Optional[str] = None  # Added table_used field