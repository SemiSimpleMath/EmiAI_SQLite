# EmiAi - Extensible Multi-Agent AI Framework

EmiAi is a powerful, flexible framework for building, managing, and deploying multi-agent AI systems. With its visual flow editor and robust state management, EmiAi makes it easy to create complex agent interactions without getting lost in implementation details.

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- Node.js 14+
- Git
- OpenAI API key (or other LLM provider)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/EmiAi.git
cd EmiAi

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd app/assistant/agent_flow
npm install
cd ../../..

# Set up environment variables
export OPENAI_API_KEY=your_api_key_here
export FLASK_SECRET_KEY=your_secret_key
```

### Running the System

```bash
# Start the backend server
python run.py

# In a new terminal, start the frontend
cd app/assistant/agent_flow
npm start
```

Access the visual agent flow editor at `http://localhost:3000` or the API at `https://localhost:8000`

## 🎯 Key Features

- **Visual Flow Editor**: Design agent systems graphically with an intuitive interface
- **Blackboard Architecture**: Powerful state management for agent coordination
- **Flexible Agent System**: Create specialized agents for different tasks
- **Comprehensive Tool Registry**: Pre-built tools for common operations
- **Template System**: Start with pre-configured agent patterns
- **Extensible Design**: Add custom agents, tools, and capabilities

## 📚 Documentation

Full documentation is available in the [docs](./docs) directory:

- [Getting Started Guide](./docs/getting_started/quick_start.md)
- [Basic Concepts](./docs/getting_started/basic_concepts.md)
- [Tutorials](./docs/tutorials/)
- [API Reference](./docs/reference/api_reference.md)

## 🧪 Beta Testing

Thank you for participating in the beta test! Your feedback is invaluable for improving EmiAi.

- Please report issues through [GitHub Issues](https://github.com/yourusername/EmiAi/issues)
- For suggestions or questions, contact [your contact information]
- Check the [Known Limitations](./docs/known_limitations.md) document for existing issues

## 📋 License

[Your chosen license]he API:**
   ```python
   import requests
   
   # Send a request to your manager
   response = requests.post(
       "https://localhost:8000/api/process",
       json={
           "manager": "MyFirstManager",
           "message": "What is the capital of France?"
       }
   )
   
   print(response.json())
   ```

## Next Steps

- Learn about [Basic Concepts](./basic_concepts.md)
- Try the [Creating a Custom Agent](../tutorials/creating_first_agent.md) tutorial
- Explore [Agent Patterns](../guides/agent_patterns.md)