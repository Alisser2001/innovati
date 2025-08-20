import asyncio
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings
from typing import Any, Dict

class GeminiClient:
    def __init__(self):
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("Falta GEMINI_API_KEY")
        model_name = settings.GEMINI_MODEL
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.2,
            max_output_tokens=512
        )

    async def ainvoke(self, messages: list[Dict[str, Any]]):
        return await self.llm.ainvoke(messages)

    
