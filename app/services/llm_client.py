#llm_client.py
from typing import List, Dict, Any

import base64
import mimetypes
from pathlib import Path
import re

from openai import OpenAI

import os
import threading
import sys

from app.assistant.utils.logging_config import get_logger
from app.assistant.performance.performance_monitor import performance_monitor
logger = get_logger(__name__)


def _repo_root_from_here() -> Path:
    # app/services/llm_client.py -> repo root
    return Path(__file__).resolve().parents[2]


def _resolve_local_upload_image_path(path: str) -> str:
    """
    Deterministically resolve local image references.

    In many places, agents only see the *filename* (e.g. "mcp_....png") in summaries.
    The system is responsible for expanding that into an absolute path under uploads/temp/.
    """
    s = (path or "").strip()
    if not s:
        return s

    p = Path(s)
    if p.is_absolute():
        return str(p)

    # Filename-only or relative: assume it lives under repo uploads/temp/.
    fname = p.name
    root = _repo_root_from_here()
    cand = (root / "uploads" / "temp" / fname).resolve()
    if cand.exists():
        return str(cand)

    # Fallback: try repo_root/<relative> if caller passed something like "uploads/temp/foo.png".
    cand2 = (root / p).resolve()
    if cand2.exists():
        return str(cand2)

    # Keep original (so caller can see what failed).
    return s


def _image_file_to_data_uri(path: str) -> str:
    path = _resolve_local_upload_image_path(path)
    p = Path(path)
    data = p.read_bytes()
    mime, _ = mimetypes.guess_type(str(p))
    if not mime:
        # Default to PNG since Playwright screenshots are often PNG.
        mime = "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _normalize_openai_responses_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize legacy chat-style message content into the OpenAI Responses API
    "content blocks" format, while preserving existing text-only behavior.

    Supports:
    - content: "string"  (left as-is)
    - content: [{"type":"text","text":...}]  -> input_text
    - content: [{"type":"image_url","image_url":{"url":...}}] -> input_image
    - content: [{"type":"image_path","path":"..."}] -> input_image (data URI)
    - content: [{"type":"image_base64","data":"...","mime":"image/png"}] -> input_image (data URI)
    - content: [{"type":"input_text",...}] / [{"type":"input_image",...}] (passed through)
    """
    normalized: List[Dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue

        out = dict(msg)
        content = out.get("content")

        # Common case: plain string content (keep for backwards compatibility).
        if content is None or isinstance(content, str):
            normalized.append(out)
            continue

        # Responses API prefers a list of content blocks for multimodal.
        if isinstance(content, list):
            blocks: List[Dict[str, Any]] = []
            for part in content:
                if isinstance(part, str):
                    blocks.append({"type": "input_text", "text": part})
                    continue
                if not isinstance(part, dict):
                    continue

                ptype = part.get("type")

                if ptype in ("input_text",):
                    blocks.append({"type": "input_text", "text": part.get("text") or ""})
                    continue
                if ptype in ("text",):
                    blocks.append({"type": "input_text", "text": part.get("text") or ""})
                    continue

                if ptype in ("input_image",):
                    image_url = part.get("image_url") or part.get("url")
                    if image_url:
                        blocks.append({"type": "input_image", "image_url": image_url})
                    continue
                if ptype in ("image_url",):
                    # Chat-completions style: {"image_url": {"url": "..."}}
                    image_url_obj = part.get("image_url")
                    if isinstance(image_url_obj, dict) and image_url_obj.get("url"):
                        blocks.append({"type": "input_image", "image_url": image_url_obj["url"]})
                    elif isinstance(image_url_obj, str):
                        blocks.append({"type": "input_image", "image_url": image_url_obj})
                    continue

                if ptype == "image_path":
                    path = part.get("path")
                    if path:
                        try:
                            resolved = _resolve_local_upload_image_path(str(path))
                            blocks.append({"type": "input_image", "image_url": _image_file_to_data_uri(resolved)})
                        except FileNotFoundError:
                            # Do NOT crash the pipeline if an image path is missing.
                            # Convert to a text hint and continue text-only.
                            blocks.append(
                                {
                                    "type": "input_text",
                                    "text": f"[image load failed: file not found: {path}]",
                                }
                            )
                        except Exception as e:
                            blocks.append(
                                {
                                    "type": "input_text",
                                    "text": f"[image load failed: {path} ({e})]",
                                }
                            )
                    continue

                if ptype == "image_base64":
                    data = part.get("data") or ""
                    mime = part.get("mime") or "image/png"
                    if data:
                        blocks.append({"type": "input_image", "image_url": f"data:{mime};base64,{data}"})
                    continue

                # Unknown part type: best-effort stringify as text so we don't drop signal.
                try:
                    import json as _json
                    blocks.append({"type": "input_text", "text": _json.dumps(part, ensure_ascii=True)})
                except Exception:
                    blocks.append({"type": "input_text", "text": str(part)})

            out["content"] = blocks
            normalized.append(out)
            continue

        # If some caller passed a dict, stringify it rather than breaking the request.
        try:
            import json as _json
            out["content"] = _json.dumps(content, ensure_ascii=True)
        except Exception:
            out["content"] = str(content)
        normalized.append(out)

    return normalized


def _strip_markdown_code_fences(text: str) -> str:
    """
    Remove surrounding markdown code fences (``` or ```json) if present.
    Best-effort; returns original if no fences found.
    """
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    # Common pattern: ```json\n{...}\n```
    # Remove first line fence and trailing fence.
    lines = s.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```"):
        # Drop leading fence line
        lines = lines[1:]
        # Drop trailing fence line(s)
        while lines and lines[-1].strip().startswith("```"):
            lines.pop()
        return "\n".join(lines).strip()
    return s


def _parse_first_json_object(text: str) -> Any:
    """
    Parse the first valid JSON value from a string, ignoring any trailing garbage.
    This avoids failures like: `Extra data: line ...` when the model emits multiple
    JSON objects or appends commentary.
    """
    import json as _json

    s = _strip_markdown_code_fences(text)
    s = s.lstrip("\ufeff").strip()  # remove BOM if present
    if not s:
        raise ValueError("empty json text")

    decoder = _json.JSONDecoder()

    # Fast path: try from the beginning (after whitespace).
    try:
        obj, _idx = decoder.raw_decode(s)
        return obj
    except Exception:
        pass

    # Best-effort: find first likely JSON start.
    m = re.search(r"[\{\[]", s)
    if not m:
        raise ValueError("no json object/array start found")
    start = m.start()
    obj, _idx = decoder.raw_decode(s[start:])
    return obj


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
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # Thread-safe singleton init: parallel web_managers can create LLMs concurrently.
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(OpenAILLM, cls).__new__(cls)
                    cls._instance._init_once(*args, **kwargs)
        else:
            # If another thread created the instance but hasn't fully initialized yet,
            # ensure we don't return a partially constructed object.
            if not hasattr(cls._instance, "client"):
                with cls._instance_lock:
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
        messages = _normalize_openai_responses_messages(messages)
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
            # Use explicit JSON Schema structured outputs so we can sanitize schemas
            # for OpenAI requirements (e.g., root additionalProperties=false).
            #
            # `responses.parse(text_format=<PydanticModel>)` relies on auto-generated schemas,
            # which can fail OpenAI validation for dynamically generated models.
            from pydantic import BaseModel as _BaseModel  # local import for clarity

            if isinstance(response_format, type) and issubclass(response_format, _BaseModel):
                text_cfg = pydantic_to_openai_schema(response_format)
            elif isinstance(response_format, dict):
                # Allow either:
                # - already-prepared Responses API text config: {"format": {...}}
                # - a raw JSON Schema object: {"type":"object", ...}
                if "format" in response_format:
                    text_cfg = response_format
                else:
                    # Treat as raw JSON Schema and wrap for Responses API.
                    schema = dict(response_format)
                    try:
                        sanitize_schema(schema)
                        schema = inline_refs(schema)
                        sanitize_schema(schema)
                    except Exception:
                        pass
                    text_cfg = {
                        "format": {
                            "type": "json_schema",
                            "name": "EmiStructuredOutput",
                            "schema": schema,
                            "strict": True,
                        }
                    }
            else:
                raise ValueError(f"Invalid response format: {type(response_format)}")

            is_gpt5_family = isinstance(model, str) and model.startswith("gpt-5")
            kwargs: dict[str, Any] = {
                "model": model,
                "input": messages,
                "text": text_cfg,
                "timeout": timeout,
            }
            # gpt-5* rejects `temperature`; also omit if None.
            if not is_gpt5_family and temperature is not None:
                kwargs["temperature"] = temperature
            if is_gpt5_family:
                kwargs["reasoning"] = {"effort": "medium"}

            # Safety: ensure unsupported params are not sent to gpt-5* even if
            # something upstream injected them into kwargs.
            if is_gpt5_family:
                kwargs.pop("temperature", None)

            response = self.client.responses.create(**kwargs)

            # Extract and parse the JSON text content.
            raw_text = None
            try:
                raw_text = response.output[0].content[0].text  # type: ignore[attr-defined]
            except Exception:
                raw_text = getattr(response, "output_text", None)

            if not isinstance(raw_text, str) or not raw_text.strip():
                raise ValueError("OpenAI response contained no parsable text output")

            result = _parse_first_json_object(raw_text)
            if not isinstance(result, dict):
                raise ValueError("Structured output must be a JSON object")
            return result

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
        messages = _normalize_openai_responses_messages(messages)
        # Get model and response format from `send_params`
        json_schema = send_params.get('response_format')
        # json_schema = pydantic_to_openai_schema(response_format) this is if the schema is in pydantic and you want to convert it to json

        print("json response format is", json_schema)

        model = send_params.get('model', "gpt-4o-2024-08-06")
        temperature = send_params.get('temperature')
        timeout = send_params.get('timeout', 120)

        # Allow passing a Pydantic model here too.
        try:
            from pydantic import BaseModel as _BaseModel  # type: ignore
            if isinstance(json_schema, type) and issubclass(json_schema, _BaseModel):
                json_schema = pydantic_to_openai_schema(json_schema)
        except Exception:
            pass

        if json_schema is None:
            logger.error("Response format is None. Please ensure a valid response format is provided.")
            raise ValueError("Invalid response format: None")

        # Log which model is being used with all parameters
        logger.info(f"Using model: {model} for structured JSON output, with temperature {temperature}, timeout {timeout}s.")
        print(f"🔍 Using model: {model} for structured JSON output (temp: {temperature}, timeout: {timeout}s)")

        # Start timing the LLM call
        timer_id = performance_monitor.start_timer('llm_structured_output_json', f"{model}_{len(messages)}")

        try:
            # Accept either raw JSON schema or already-wrapped {"format": {...}}.
            text_cfg: dict[str, Any]
            if isinstance(json_schema, dict) and "format" in json_schema:
                text_cfg = json_schema
            else:
                schema = dict(json_schema) if isinstance(json_schema, dict) else {"type": "object"}
                try:
                    sanitize_schema(schema)
                    schema = inline_refs(schema)
                    sanitize_schema(schema)
                except Exception:
                    pass
                text_cfg = {
                    "format": {
                        "type": "json_schema",
                        "name": "EmiStructuredOutput",
                        "schema": schema,
                        "strict": True,
                    }
                }

            kwargs = {
                "model": model,
                "input": messages,
                "text": text_cfg,
                "timeout": timeout,  # Configurable timeout, defaults to 120 seconds
            }
            # gpt-5* rejects `temperature`; also omit if None.
            is_gpt5_family = isinstance(model, str) and model.startswith("gpt-5")
            if not is_gpt5_family and temperature is not None:
                kwargs["temperature"] = temperature

            # Safety: ensure unsupported params are not sent to gpt-5* even if
            # something upstream injected them into kwargs.
            if is_gpt5_family:
                kwargs.pop("temperature", None)

            response = self.client.responses.create(**kwargs)
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
    """
    Make a Pydantic/JSON schema compatible with OpenAI Structured Outputs.

    Key requirement (OpenAI): every object schema must have `additionalProperties: false`
    unless it explicitly declares typed additionalProperties.

    Pydantic sometimes emits object-like schemas without an explicit `type: object`
    at the point we see them (e.g., via refs/anyOf), so we treat any schema that
    has `properties` as object-ish.
    """
    if not isinstance(schema_part, dict):
        return schema_part

    t = schema_part.get("type")
    type_list = t if isinstance(t, list) else None
    is_objectish = (
        t == "object"
        or (isinstance(type_list, list) and "object" in type_list)
        or isinstance(schema_part.get("properties"), dict)
    )

    if is_objectish:
        # Enforce additionalProperties=false unless explicitly typed.
        if "additionalProperties" not in schema_part:
            schema_part["additionalProperties"] = False
        elif isinstance(schema_part.get("additionalProperties"), dict):
            # Respect typed additionalProperties (e.g., {"type": "string"})
            pass

        # OpenAI Structured Outputs (strict JSON schema) expects `required` to be present
        # and to include *every* key in `properties`. Optionality should be expressed via
        # nullable types (e.g., anyOf: [<type>, null]) rather than omitting from required.
        props = schema_part.get("properties")
        if isinstance(props, dict) and props:
            schema_part["required"] = sorted([k for k in props.keys() if isinstance(k, str) and k])

    # OpenAI rejects "default" in many schema positions; drop it.
    if "default" in schema_part:
        schema_part.pop("default")

    # Recurse common schema containers.
    props = schema_part.get("properties")
    if isinstance(props, dict):
        for prop in props.values():
            if isinstance(prop, dict):
                sanitize_schema(prop)

    items = schema_part.get("items")
    if isinstance(items, dict):
        sanitize_schema(items)
    elif isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                sanitize_schema(it)

    for key in ("anyOf", "oneOf", "allOf"):
        alts = schema_part.get(key)
        if isinstance(alts, list):
            for alt in alts:
                if isinstance(alt, dict):
                    sanitize_schema(alt)

    if "definitions" in schema_part and isinstance(schema_part["definitions"], dict):
        for value in schema_part["definitions"].values():
            if isinstance(value, dict):
                sanitize_schema(value)
    if "$defs" in schema_part and isinstance(schema_part["$defs"], dict):
        for value in schema_part["$defs"].values():
            if isinstance(value, dict):
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
    # Inline can introduce object schemas in new positions; sanitize again to
    # enforce OpenAI Structured Outputs requirements everywhere.
    sanitize_schema(schema)
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
