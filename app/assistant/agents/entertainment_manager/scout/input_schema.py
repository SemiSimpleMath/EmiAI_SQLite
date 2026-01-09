from pydantic import BaseModel, Field

class scout_args(BaseModel):
    """
    Arguments for the find_node agent.
    """
    agent_task: str = Field(
        ...,
        description="All information that the scout needs to do its job."
    )

class scout_arguments(BaseModel):
    arguments: scout_args
