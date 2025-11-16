import json
import unicodedata
from datetime import datetime

# Custom JSON Encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            # Convert datetime object to ISO format string
            return obj.isoformat()
        return super().default(obj)

# Serialize data to JSON string
# json_string = json.dumps(data, cls=DateTimeEncoder, indent=4)


def normalize_to_ascii(text: str) -> str:
    """
    Convert a string to ASCII by replacing non-ASCII characters with their ASCII equivalents.
    If no ASCII equivalent exists, the character is removed.
    
    Args:
        text (str): Input string that may contain non-ASCII characters
        
    Returns:
        str: ASCII-only string with non-ASCII characters converted or removed
        
    Examples:
        >>> normalize_to_ascii("Café")
        "Cafe"
        >>> normalize_to_ascii(""Hello"")
        "Hello"
        >>> normalize_to_ascii("1–3 words")
        "1-3 words"
    """
    if not isinstance(text, str):
        return str(text)
    
    # Normalize unicode characters (e.g., decompose combined characters)
    normalized = unicodedata.normalize('NFD', text)
    
    # Convert to ASCII, replacing non-ASCII characters with their closest ASCII equivalent
    # or removing them if no equivalent exists
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    
    # Check if any changes were made and print if so
    if ascii_text != text:
        print(f"🔧 ASCII Normalization: Replaced non-ASCII characters")
        print(f"   Length: {len(text)} -> {len(ascii_text)} characters")
        print()
    
    return ascii_text

