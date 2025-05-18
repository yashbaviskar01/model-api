from fastapi import APIRouter, HTTPException
from app.schemas.schema import PromptUpdate
from app.utils.s3_prompts_config import get_prompt, update_prompt

router = APIRouter()

@router.get("/prompts/{prompt_name}")
async def read_prompt(prompt_name: str):
    """
    Reads the prompt content from S3 for the given prompt_name.
    """
    content = get_prompt(prompt_name)
    if not content:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_name}' not found.")
    return {"prompt_name": prompt_name, "content": content}

@router.put("/prompts/update")
async def update_prompt_endpoint(prompt_update: PromptUpdate):
    """
    Updates the prompt content in S3 using an input payload.
    Expects a JSON body containing the prompt name and new content.
    """
    success = update_prompt(prompt_update.prompt_name, prompt_update.content)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to update prompt '{prompt_update.prompt_name}'.")
    return {"message": f"Prompt '{prompt_update.prompt_name}' updated successfully."}
