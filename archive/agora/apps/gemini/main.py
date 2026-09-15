from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from core.ai.gemini import GeminiAgent
import os

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

GEMINI_KEY = os.getenv("GEMINI_KEY", "")
gemini_agent = GeminiAgent(api_key=GEMINI_KEY)

@app.post("/generate")
async def generate_text(request: PromptRequest):
    if not GEMINI_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_KEY not set")
    try:
        result = await gemini_agent.generate(request.prompt)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
