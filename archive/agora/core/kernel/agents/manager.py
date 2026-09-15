# ~/core/kernel/agents/manager.py

def get_ai_agent(model_name: str, api_key: str):
    if model_name == "gemini":
        from core.ai.gemini import GeminiAgent
        return GeminiAgent(api_key)
    else:
        raise ValueError(f"Unsupported model: {model_name}")
