"""
Utility to get the assistant's name from configuration
"""
from pathlib import Path
import json
from typing import Optional

def get_assistant_name() -> str:
    """
    Get the assistant's name from resource_assistant_data.json
    Falls back to 'Emi' if not found
    
    Returns:
        str: The assistant's name
    """
    try:
        resources_dir = Path(__file__).resolve().parents[3] / 'resources'
        assistant_data_file = resources_dir / 'resource_assistant_data.json'
        
        if assistant_data_file.exists():
            with open(assistant_data_file, 'r') as f:
                assistant_data = json.load(f)
                return assistant_data.get('name', 'Emi')
        
        return 'Emi'
    except Exception as e:
        print(f"Warning: Could not load assistant name: {e}")
        return 'Emi'


