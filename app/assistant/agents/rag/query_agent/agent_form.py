from pydantic import BaseModel


class AgentForm(BaseModel):
    my_thoughts: str
    query: str
    query_list: str