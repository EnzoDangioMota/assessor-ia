from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_MODEL_FAST,
)

llmGemini = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0.7,
    top_p=0.95,
    google_api_key=GEMINI_API_KEY,
)

llmGroq = ChatGroq(
    model=GROQ_MODEL,
    temperature=0.7,
    groq_api_key=GROQ_API_KEY,
)

llmRapido = ChatGroq(
    model=GROQ_MODEL_FAST,
    temperature=0.0,
    groq_api_key=GROQ_API_KEY,
)

llm = llmGroq.with_fallbacks([llmGemini])