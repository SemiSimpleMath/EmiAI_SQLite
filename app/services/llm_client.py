#llm_client.py
from typing import List, Dict

from openai import OpenAI

import os
import sys

from app.assistant.utils.logging_config import get_logger
from app.assistant.performance.performance_monitor import performance_monitor
logger = get_logger(__name__)


def _handle_fatal_quota_error(error_msg: str, context: str = ""):
    """
    Handle fatal LLM quota errors by logging and forcing program exit.
    Uses os._exit() because sys.exit() doesn't work reliably in threads.
    """
    logger.critical(f"❌ FATAL: LLM Quota Exhausted")
    logger.critical(f"   Context: {context}")
    logger.critical(f"   Error: {error_msg}")
    logger.critical(f"🛑 Forcing program exit to prevent data corruption")
    
    print(f"\n{'=' * 80}")
    print(f"❌ CRITICAL ERROR: LLM Quota Exhausted")
    print(f"{'=' * 80}")
    print(f"Context: {context}")
    print(f"Error: {error_msg}")
    print(f"{'=' * 80}")
    print(f"🛑 Program terminated. Please check your LLM quota and billing.")
    print(f"{'=' * 80}\n")
    
    # Use os._exit() instead of sys.exit() - works in threads and bypasses exception handlers
    os._exit(1)

# print("\nthe key is: ", os.environ.get('OPENAI_API_KEY'))  # Should return your API key

# Removed: Time checking moved to maintenance manager for surgical control


class BaseLLMProvider:
    def send_query(self, messages, **send_request):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def send_function_query(self, messages, **send_request):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def build_messages(self, **send_params):
        raise NotImplementedError("This method should be implemented by subclasses.")

    def stream_response_to_socket(self, messages, socket_id, user_id, audio_output, **kwargs):
        raise NotImplementedError("This method should be implemented by subclasses.")

class OpenAILLM(BaseLLMProvider):
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(OpenAILLM, cls).__new__(cls)
            cls._instance._init_once(*args, **kwargs)
        return cls._instance

    def _init_once(self, api_key=None, engine="gpt-3.5-turbo", temperature=0.1, **kwargs):
        """Initializes OpenAILLM once."""
        if hasattr(self, "client"):  # Prevent reinitialization
            return

        self.api_key = os.environ.get('OPENAI_API_KEY')
        self.engine = engine
        self.temperature = temperature
        self.client = OpenAI(api_key=self.api_key)  # Shared OpenAI client instance

        # Apply additional settings if needed
        for key, value in kwargs.items():
            setattr(self, key, value)


    def structured_output(self, messages, **send_params):
        # Get model and response format from `send_params`
        response_format = send_params.get('response_format')
        model = send_params.get('engine', "gpt-4.1-mini")
        temperature = send_params.get('temperature', None)
        timeout = send_params.get('timeout', 240)

        # Check if response_format is None and log an error if so
        if response_format is None:
            logger.error("Response format is None. Please ensure a valid response format is provided.")
            # Optionally, raise an exception or handle it accordingly
            raise ValueError("Invalid response format: None")

        # print(messages)

        # Log which model is being used with all parameters
        logger.info(f"Using model: {model} for structured output, with temperature {temperature}, timeout {timeout}s.")
        print(f"🔍 Using model: {model} for structured output (temp: {temperature}, timeout: {timeout}s)")

        # Start timing the LLM call
        timer_id = performance_monitor.start_timer('llm_structured_output', f"{model}_{len(messages)}")
        
        try:
            if model in ["gpt-5, gpt-5-mini, gpt-5-nano"]:
                response = self.client.responses.parse(
                    model=model,
                    input=messages,
                    temperature=1,
                    text_format=response_format,
                    reasoning={
                        "effort": "medium",
                    }
                )
            else:
                response = self.client.responses.parse(
                    model=model,
                    input=messages,
                    temperature=temperature,
                    text_format=response_format,
                )

            result = response.output_parsed
            
            return result.model_dump()

        except Exception as e:
            # End timing and record error
            performance_monitor.end_timer(timer_id, {
                'status': 'error',
                'model': model,
                'message_count': len(messages),
                'temperature': temperature,
                'timeout': timeout,
                'error': str(e)
            })
            
            logger.error(f"Error processing input function_query: {e}")
            error_str = str(e).lower()
            
            # FATAL: Quota errors require immediate program exit
            if "quota" in error_str or "insufficient_quota" in error_str:
                _handle_fatal_quota_error(str(e), f"structured_output (model: {model})")
            
            # Return a more detailed error message for non-fatal errors
            if "timeout" in error_str:
                return f"LLM request timed out after {timeout} seconds"
            elif "rate limit" in error_str:
                return "LLM rate limit exceeded"
            else:
                return f"LLM error: {str(e)}"

    def structured_output_json(self, messages, **send_params):
        # Get model and response format from `send_params`
        json_schema = send_params.get('response_format')
        # json_schema = pydantic_to_openai_schema(response_format) this is if the schema is in pydantic and you want to convert it to json

        print("json response format is", json_schema)

        model = send_params.get('model', "gpt-4o-2024-08-06")
        temperature = send_params.get('temperature')
        timeout = send_params.get('timeout', 120)

        if json_schema is None:
            logger.error("Response format is None. Please ensure a valid response format is provided.")
            raise ValueError("Invalid response format: None")

        # Log which model is being used with all parameters
        logger.info(f"Using model: {model} for structured JSON output, with temperature {temperature}, timeout {timeout}s.")
        print(f"🔍 Using model: {model} for structured JSON output (temp: {temperature}, timeout: {timeout}s)")

        # Start timing the LLM call
        timer_id = performance_monitor.start_timer('llm_structured_output_json', f"{model}_{len(messages)}")

        try:
            # Use raw JSON Schema with structured outputs
            response = self.client.responses.create(
                model=model,
                input=messages,
                text = json_schema,
                timeout=timeout,  # Configurable timeout, defaults to 120 seconds
                temperature=temperature
            )
            print("\n\n\n=====DEBUG============")
            print(response)
            print("\n=====DEBUG============\n\n\n")
            event = json.loads(response.output[0].content[0].text)
            print("\n\n\n")
            print("Output of OPENAI LLM: ", event)
            print("\n\n\n")

            # Extract detailed token usage information from responses API
            usage = getattr(response, 'usage', None)
            if usage:
                prompt_tokens = getattr(usage, 'prompt_tokens', 0)
                completion_tokens = getattr(usage, 'completion_tokens', 0)
                cached_tokens = getattr(usage, 'cached_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', 0)
                
                # Log detailed token usage
                logger.info(f"Token usage (JSON) - Input: {prompt_tokens}, Output: {completion_tokens}, Cached: {cached_tokens}, Total: {total_tokens}")
                print(f"💰 Token usage (JSON) - Input: {prompt_tokens}, Output: {completion_tokens}, Cached: {cached_tokens}, Total: {total_tokens}")
            else:
                prompt_tokens = completion_tokens = cached_tokens = total_tokens = None
                logger.warning("No token usage information available in JSON response")
                print("⚠️ No token usage information available (JSON)")

            # End timing and record success
            performance_monitor.end_timer(timer_id, {
                'status': 'success',
                'model': model,
                'message_count': len(messages),
                'temperature': temperature,
                'timeout': timeout,
                'total_tokens': total_tokens,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'cached_tokens': cached_tokens
            })

            return event

        except Exception as e:
            # End timing and record error
            performance_monitor.end_timer(timer_id, {
                'status': 'error',
                'model': model,
                'message_count': len(messages),
                'temperature': temperature,
                'timeout': timeout,
                'error': str(e)
            })
            
            logger.error(f"Error processing input function_query: {e}")
            error_str = str(e).lower()
            
            # FATAL: Quota errors require immediate program exit
            if "quota" in error_str or "insufficient_quota" in error_str:
                _handle_fatal_quota_error(str(e), f"structured_output_json (model: {model})")
            
            # Return a more detailed error message for non-fatal errors
            if "timeout" in error_str:
                return f"LLM request timed out after {timeout} seconds"
            elif "rate limit" in error_str:
                return "LLM rate limit exceeded"
            else:
                return f"LLM error: {str(e)}"

class GeminiLLM(BaseLLMProvider):
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(GeminiLLM, cls).__new__(cls)
            cls._instance._init_once(*args, **kwargs)
        return cls._instance

    def _init_once(self, api_key=None, engine="gemini-1.5-flash", temperature=0.1, **kwargs):
        """Initializes GeminiLLM once using the new google-genai package."""
        if hasattr(self, "client"):
            return

        try:
            from google import genai
            from google.genai import types
            self.genai = genai
            self.types = types
        except ImportError:
            logger.error("google-genai is not installed. Please run 'pip install google-genai'")
            raise

        self.api_key = api_key or os.environ.get('GOOGLE_API_KEY')
        if not self.api_key:
             logger.warning("GOOGLE_API_KEY not found in environment. Gemini will fail until set.")
        
        # New API uses Client instead of configure
        self.client = self.genai.Client(api_key=self.api_key)
        self.engine = engine
        self.temperature = temperature
        
        # Apply additional settings if needed
        for key, value in kwargs.items():
            setattr(self, key, value)

    def _convert_messages_to_contents(self, messages: List[Dict]):
        """Converts OpenAI-style messages to new Gemini contents format."""
        from typing import Tuple, Optional
        system_instruction = None
        contents = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(content)
            elif role == "assistant":
                # For multi-turn, we'd need to handle this differently
                # For now, append as user context
                pass
                
        # Join all user messages
        combined_content = "\n\n".join(contents) if contents else ""
        return system_instruction, combined_content

    def structured_output(self, messages, **send_params):
        response_format = send_params.get('response_format')
        model_name = send_params.get('engine', self.engine)
        temperature = send_params.get('temperature', self.temperature)
        timeout = send_params.get('timeout', 240)

        if response_format is None:
            logger.error("Response format is None for Gemini structured output.")
            raise ValueError("Invalid response format: None")

        logger.info(f"Using Gemini model: {model_name} for structured output")
        print(f"🔍 Using Gemini model: {model_name} (temp: {temperature})")
        
        timer_id = performance_monitor.start_timer('llm_structured_output_gemini', f"{model_name}_{len(messages)}")
        
        try:
            system_instruction, content = self._convert_messages_to_contents(messages)
            
            # Build the full prompt with system instruction
            if system_instruction:
                full_prompt = f"{system_instruction}\n\n{content}"
            else:
                full_prompt = content
            
            # New API accepts Pydantic models directly!
            response = self.client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=self.types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=response_format,  # Pass Pydantic model directly
                    temperature=temperature,
                )
            )
            
            # New API has .text attribute for JSON string
            import json as json_lib
            result_dict = json_lib.loads(response.text)
            
            performance_monitor.end_timer(timer_id, {'status': 'success', 'model': model_name})
            logger.info(f"✅ Gemini response received successfully")
            return result_dict

        except Exception as e:
            performance_monitor.end_timer(timer_id, {'status': 'error', 'model': model_name, 'error': str(e)})
            logger.error(f"Gemini LLM error: {e}", exc_info=True)
            
            # Return a dict to match expected structure
            return {
                "error": True,
                "message": f"Gemini error: {str(e)}",
                "model": model_name
            }

    def structured_output_json(self, messages, **send_params):
        """Gemini equivalent for structured JSON output."""
        return self.structured_output(messages, **send_params)


class LLMInterface:
    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm_provider = llm_provider

    def structured_output(self, message, use_json=False, **params):
        if not use_json:
            response = self.llm_provider.structured_output(message, **params)
        else:
            response = self.llm_provider.structured_output_json(message, **params)
        return response
    def structured_output_json(self, message, **params):

        response = self.llm_provider.structured_output_json(message, **params)
        return response



from pydantic import BaseModel
import json

def sanitize_schema(schema_part: dict):
    if "type" in schema_part and schema_part["type"] == "object":
        # Only set additionalProperties=False if it's not already validly defined
        # Only apply to top-level models or defined objects, not item definitions
        if "type" in schema_part and schema_part["type"] == "object":
            if "additionalProperties" not in schema_part:
                schema_part["additionalProperties"] = False
            elif isinstance(schema_part["additionalProperties"], dict):
                # Respect typed additionalProperties (e.g., {"type": "string"})
                pass
        if "default" in schema_part:
            schema_part.pop("default")
        for prop in schema_part.get("properties", {}).values():
            sanitize_schema(prop)
    elif "type" in schema_part and isinstance(schema_part["type"], list):
        if "default" in schema_part:
            schema_part.pop("default")
    if "definitions" in schema_part:
        for value in schema_part["definitions"].values():
            sanitize_schema(value)
    if "$defs" in schema_part:
        for value in schema_part["$defs"].values():
            sanitize_schema(value)
    return schema_part

def inline_refs(schema: dict, root_schema: dict = None) -> dict:
    """
    Recursively replace local $ref occurrences with their actual definitions from root_schema.
    """
    if root_schema is None:
        root_schema = schema

    if isinstance(schema, dict):
        if '$ref' in schema:
            ref = schema['$ref']
            # Only support local references like "#/path/to/definition"
            if not ref.startswith("#/"):
                raise ValueError(f"Only local references are supported, got {ref}")
            # Traverse the root schema using the reference path
            parts = ref[2:].split("/")  # remove "#/" and split
            ref_value = root_schema
            for part in parts:
                if part not in ref_value:
                    raise ValueError(f"Reference {ref} not found in schema")
                ref_value = ref_value[part]
            # Inline the referenced value (and process nested refs)
            return inline_refs(ref_value, root_schema)
        else:
            # Recursively process dictionary items
            return {key: inline_refs(value, root_schema) for key, value in schema.items()}
    elif isinstance(schema, list):
        return [inline_refs(item, root_schema) for item in schema]
    else:
        return schema

def pydantic_to_openai_schema(model: type[BaseModel], name: str | None = None, strict: bool = True) -> dict:
    schema = model.model_json_schema()
    # Sanitize the schema first to set additionalProperties and remove unwanted defaults.
    sanitize_schema(schema)
    # Inline any $ref references.
    schema = inline_refs(schema)
    # Remove leftover definitions containers
    schema.pop("$defs", None)
    schema.pop("definitions", None)

    return {
        "format": {
            "type": "json_schema",
            "name": name or model.__name__,
            "schema": schema,
            "strict": strict
        }
    }

if __name__ == "__main__":
    class AgentForm(BaseModel):
        final_answer_content: str
        summary: str
        important_links: List[Dict[str, str]]

    schema_output = pydantic_to_openai_schema(AgentForm)
    print(json.dumps(schema_output, indent=2))
