from pydantic import BaseModel, Field
from typing import List, Optional


class JsonLocation(BaseModel):
    """A location in the JSON where relevant data was found."""
    path: str = Field(description="JSON path like 'food.likes[2]' or 'drinks.coffee.cutoff_time'")
    current_value: str = Field(description="Current value at this location (as string)")
    relevance: str = Field(description="Why this location is relevant to the query")


class AgentForm(BaseModel):
    """JSON Finder output: locations of relevant data."""
    
    locations: List[JsonLocation] = Field(
        default_factory=list,
        description="List of JSON paths where relevant data was found"
    )
    
    suggested_insert_path: Optional[str] = Field(
        default=None,
        description="If no existing data found, suggest where to insert new data (e.g., 'food.likes')"
    )
    
    reasoning: str = Field(
        description="Explanation of search strategy and findings"
    )


