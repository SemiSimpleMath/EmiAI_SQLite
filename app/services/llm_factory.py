# llm_factory.py
from typing import List, Dict

from pydantic import BaseModel

from app.services.llm_client import LLMInterface
from app.configs.llm_classes_dict import get_llm_class

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class LLMFactory:
    _llm_interfaces = {}  # Dict of provider_name -> LLMInterface singleton

    @staticmethod
    def get_llm_interface(**kwargs):
        provider_name = kwargs.get('llm_provider', 'openai')
        
        # Return cached interface if it exists for this provider
        if provider_name in LLMFactory._llm_interfaces:
            return LLMFactory._llm_interfaces[provider_name]
        
        # Create new singleton for this provider
        LLM_class = get_llm_class(provider_name)
        if not LLM_class:
            raise ValueError(f"Unsupported LLM provider class: {provider_name}")

        # Each provider class (OpenAILLM, GeminiLLM) is already a singleton
        llm_provider_instance = LLM_class(**kwargs)

        # Cache this provider's interface
        LLMFactory._llm_interfaces[provider_name] = LLMInterface(llm_provider_instance)
        
        logger.info(f"Created LLM interface for provider: {provider_name}")
        return LLMFactory._llm_interfaces[provider_name]

class Link(BaseModel):
    key: str
    value: str

class AgentForm(BaseModel):
    final_answer_content: str
    summary: str
    important_links: List[Link]

if __name__ == "__main__":
    # Define test parameters
    from app.services.llm_client import pydantic_to_openai_schema
    test_params = {
        "llm_provider": "openai",  # Use "openai" instead of "OpenAILLM"
        "model": "gpt-4o-mini-2024-07-18",
        "temperature": .0,
    }
    json_schema = pydantic_to_openai_schema(AgentForm)
    test_params["json_schema"]=json_schema

    print(test_params)


    import time

    # Time the interface creation
    start_interface = time.perf_counter()
    llm_interface = LLMFactory.get_llm_interface(**test_params)
    end_interface = time.perf_counter()
    print(f"LLM interface creation time: {end_interface - start_interface:.4f} seconds")

    # Define messages
    messages = [
        {"role": "system", "content": "You are you and I am me.  Let's have some fun!"},
        {"role": "user", "content": "come up with arguments for delete todo task tool"}
    ]

    # Time the LLM response
    start_response = time.perf_counter()
    test_params.update({'response_format':AgentForm})
    response = llm_interface.structured_output(messages, **test_params, use_json=True)
    end_response = time.perf_counter()
    print(f"LLM response time: {end_response - start_response:.4f} seconds")

    # Output result
    print("Structured LLM Response:", response)

    # Define messages
    messages = [
        {"role": "system", "content": "You are you and I am me.  Let's have some fun!"},
        {"role": "user", "content": "come up with any thing that matches the asked output forms"}
    ]

    # Time the LLM response
    start_response = time.perf_counter()
    response = llm_interface.structured_output_json(messages, **test_params)
    end_response = time.perf_counter()
    print(f"LLM response time: {end_response - start_response:.4f} seconds")

    # Output result
    print("Structured LLM Response:", response)



