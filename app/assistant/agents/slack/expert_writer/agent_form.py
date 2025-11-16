from pydantic import BaseModel

class Chat(BaseModel):
    chat: str

class AgentForm(BaseModel):
    what_i_am_thinking: str
    final_answer: Chat
    action: str = "exit_node"  # Always exit after generating response
