from google import genai

class GeminiAgent:
    """어떤 앱에서도 가져다 쓸 수 있는 순수 AI 에이전트"""
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-lite"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model, contents=prompt
        )
        return response.text
