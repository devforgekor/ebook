from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class OptimizationRules(BaseModel):
    remove_thoughts: bool = True
    compress_whitespace: bool = True
    shorten_urls: bool = False
    remove_system_prompt: bool = False
    max_line_length: Optional[int] = None

class OptimizeRequest(BaseModel):
    messages: List[Dict[str, Any]]
    strategy: Optional[str] = None  # "low", "medium", "high"
    rules: Optional[OptimizationRules] = None

class OptimizeResponse(BaseModel):
    optimized: List[Dict[str, Any]]
    token_saved: int
    original_tokens: int
    new_tokens: int
