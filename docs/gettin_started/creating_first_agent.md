# Creating Your First Custom Agent

This tutorial will guide you through creating your own custom agent in EmiAi.

## Understanding Agent Architecture

In EmiAi, agents follow a simple pattern:

1. They receive messages
2. They process those messages
3. They update the shared blackboard
4. They indicate the next agent to run

## Basic Agent Example

Let's create a simple agent that analyzes text sentiment:

```python
from app.assistant.lib.agents.EmiAgent import EmiAgent
from app.assistant.lib.message.Message import Message

class SentimentAnalyzer(EmiAgent):
    """Agent that analyzes the sentiment of text."""
    
    def __init__(self, name, blackboard=None):
        super().__init__(name, blackboard)
    
    def process_message(self, message: Message) -> Message:
        # 1. Get the text to analyze
        text = message.content
        
        # 2. Perform sentiment analysis
        sentiment = self._analyze_sentiment(text)
        
        # 3. Update the blackboard
        self.blackboard.update_state_value("sentiment", sentiment)
        
        # 4. Determine next agent
        self.blackboard.update_state_value("next_agent", "response_generator")
        
        # 5. Return a result message
        return Message(
            sender=self.name,
            content=f"Sentiment analysis completed: {sentiment}",
            state={"sentiment": sentiment}
        )
    
    def _analyze_sentiment(self, text):
        """Perform sentiment analysis on text."""
        # Use a tool or implement custom logic
        tool_result = self.tool_registry.execute_tool(
            "text_analyzer",
            {"text": text, "analysis_type": "sentiment"}
        )
        
        return tool_result.get("sentiment", "neutral")
```

## Registering Your Agent

To make your agent available in the system:

```python
# In your agent registry initialization
from app.assistant.lib.agents.agent_registry import AgentRegistry
from path.to.your.agent import SentimentAnalyzer

agent_registry = AgentRegistry()
agent_registry.register_agent(
    "sentiment_analyzer",
    SentimentAnalyzer,
    description="Analyzes text sentiment"
)
```

## Using Tools in Your Agent

Agents can use tools from the tool registry:

```python
def process_message(self, message: Message) -> Message:
    # Using a web search tool
    search_result = self.tool_registry.execute_tool(
        "web_search",
        {"query": message.content}
    )
    
    # Using a database tool
    db_result = self.tool_registry.execute_tool(
        "database",
        {"query": "SELECT * FROM users WHERE id = 1"}
    )
    
    # Update blackboard with results
    self.blackboard.update_state_value("search_results", search_result)
    self.blackboard.update_state_value("user_data", db_result)
    
    return Message(content="Tools executed successfully")
```

## Updating the Blackboard

The blackboard is your agent's memory and communication channel:

```python
# Adding a simple value
self.blackboard.update_state_value("key", "value")

# Adding to a list
self.blackboard.append_state_value("discoveries", "new item")

# Reading values
current_plan = self.blackboard.get_state_value("plan")
user_query = self.blackboard.get_state_value("query", "default_query")

# Setting the next agent
self.blackboard.update_state_value("next_agent", "writer_agent")
```

## Error Handling

Robust agents handle errors gracefully:

```python
def process_message(self, message: Message) -> Message:
    try:
        # Your agent logic here
        result = self._process_data(message.content)
        return Message(content=result)
    except Exception as e:
        self.logger.error(f"Error in {self.name}: {str(e)}")
        self.blackboard.update_state_value("error", str(e))
        return Message(
            content="An error occurred during processing",
            error=str(e)
        )
```

## Adding Your Agent to a Flow

Once registered, you can add your agent to a flow:

1. Open the Flow Editor at `http://localhost:3000`
2. Click "+ Add Agent"
3. Select your "SentimentAnalyzer" from the list
4. Configure any properties in the sidebar
5. Connect it to other agents in your flow
6. Save the manager configuration

## Testing Your Agent

To test your agent directly:

```python
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.lib.message.Message import Message
from path.to.your.agent import SentimentAnalyzer

# Create a test environment
blackboard = Blackboard()
agent = SentimentAnalyzer("sentiment_test", blackboard)

# Test message
message = Message(content="I really love this product! It's amazing!")

# Process message
result = agent.process_message(message)

# Check results
print(result.content)
print(blackboard.get_state_value("sentiment"))
```

## Next Steps

- Learn how to use the [Flow Editor](./using_flow_editor.md) to visually connect agents
- Explore [Custom Tools](./custom_tools.md) to extend agent capabilities
- Study [Agent Patterns](../guides/agent_patterns.md) for best practices