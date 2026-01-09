from pydantic import BaseModel


class AgentForm(BaseModel):
    """Simple confirmation output for memory updates."""
    confirmation_message: str
    changes_made: str

