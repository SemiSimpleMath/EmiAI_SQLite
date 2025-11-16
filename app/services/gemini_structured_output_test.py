
from pydantic import BaseModel
GEMINI_KEY = 'AIzaSyAxWj7BTgPYa9dWfCyEPSeDprZ-LsFH9Ls'

class ColorFood(BaseModel):
    color: str
    food: str

from google import genai

# Initialize the client
client = genai.Client(api_key=GEMINI_KEY)

# Ask Gemini to pull out color and food
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="I saw a bright yellow banana and a purple plum today. List all colors in one string under color key and food and food key.",
    config={
        "response_mime_type": "application/json",
        "response_schema": ColorFood,
    },
)

# The raw JSON response
print(response.text)
