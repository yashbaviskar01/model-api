from openai import OpenAI, OpenAIError
import os
from loguru import logger
from typing import Optional

# Initialize OpenAI API key (adjust if you have a different setup)
openai_api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=openai_api_key)

def generate_conversation_summary(question: str) -> Optional[str]:
    """
    Generates a 3-4 word conversation summary for the given question using the gpt-4o-mini model.
    
    Args:
        question (str): The user's question.
        
    Returns:
        Optional[str]: The generated summary if valid, else None.
    """
    try:
        # Construct the prompt to instruct gpt-4o-mini
        prompt_text = (
            f"Summarize the core topic of the following user query in exactly 3-4 words: {question}"
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=10,  # Expecting a very short summary so we restrict max_tokens
            temperature=0.9,
        )
        summary_text = response.choices[0].message.content
        logger.info(f"Conversation Summary :=======>> {summary_text}")

        return summary_text

    except OpenAIError as e:
        logger.error(f"Failed to generate conversation summary: {e}")
        return question