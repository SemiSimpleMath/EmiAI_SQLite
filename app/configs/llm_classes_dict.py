import os
from app.services.llm_client import OpenAILLM, GeminiLLM

# Configure logging
from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

# LLM dictionary containing different LLM providers, their class, and default parameters
LLM_CLASSES = {
    "openai": {
        "class": OpenAILLM,
        "params": {
            "api_key": os.getenv("OPENAI_API_KEY"),  # Fetch API key once
            "engine": "gpt-3.5-turbo",  # Default model
            "temperature": 0.1,  # Default temperature
        }
    },
    "gemini": {
        "class": GeminiLLM,
        "params": {
            "api_key": os.getenv("GOOGLE_API_KEY"),
            "engine": "gemini-1.5-flash",
            "temperature": 0.1,
        }
    }
}

def get_llm_class(provider_name: str):
    """Retrieve the LLM class based on provider name."""
    provider_name = provider_name.lower()
    llm_entry = LLM_CLASSES.get(provider_name)

    if not llm_entry:
        logging.error(f"Unsupported LLM provider: {provider_name}")
        return None

    return llm_entry["class"]

def get_llm_class_params(provider_name: str):
    """Retrieve the default parameters for an LLM provider."""
    provider_name = provider_name.lower()
    llm_entry = LLM_CLASSES.get(provider_name)

    if not llm_entry:
        logging.error(f"Unsupported LLM provider: {provider_name}")
        return None

    return llm_entry["params"]
