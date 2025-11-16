# gemini_llm.py
from google import genai
from pydantic import BaseModel
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

class GeminiLLM(BaseLLMProvider):
    def __init__(self, api_key=None, model="gemini-2.0-pro", temperature=0.1, **kwargs):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        self.temperature = temperature
        self.client = genai.Client(api_key=self.api_key)

    def structured_output(self, messages, **send_params):
        model = send_params.get("model", self.model)
        schema_model = send_params.get("response_format")

        if schema_model is None or not issubclass(schema_model, BaseModel):
            raise ValueError("GeminiLLM requires a Pydantic model as response_format")

        prompt = self._combine_messages(messages)

        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema_model,
                },
            )
            return response.text  # Gemini SDK already parses this if schema used
        except Exception as e:
            logger.error(f"Gemini structured_output error: {e}")
            return "Something went wrong with Gemini structured_output"

    def structured_output_json(self, messages, **send_params):
        # Gemini doesn’t need this split; just reuse structured_output
        return self.structured_output(messages, **send_params)

    def _combine_messages(self, messages):
        # Gemini does not support role separation like OpenAI yet
        return "\n".join([msg["content"] for msg in messages])
