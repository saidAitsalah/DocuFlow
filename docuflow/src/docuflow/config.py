from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_ollama import OllamaEmbeddings
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "ollama"
    llm_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"
    drive_root_folder_id: str = ""
    register_sheet_id: str = ""
    gmail_label: str = "DocuFlow/To-process"


settings = Settings()


@lru_cache
def get_llm(temperature: float = 0.0):
    """One place to swap providers: change .env, not code."""
    return init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        temperature=temperature,
    )


def get_embeddings():
    return OllamaEmbeddings(model=settings.embed_model)