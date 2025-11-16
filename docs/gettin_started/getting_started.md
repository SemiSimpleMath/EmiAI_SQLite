# EmiAi Quick Start Guide

This guide will help you create your first agent system using EmiAi.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/EmiAi.git
   cd EmiAi
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   
   cd app/assistant/agent_flow
   npm install
   cd ../../..
   ```

3. **Configure environment**
   ```bash
   # Set your OpenAI API key
   export OPENAI_API_KEY=your_api_key_here
   
   # Set a secret key for Flask
   export FLASK_SECRET_KEY=your_secret_key
   ```

## Starting the System

1. **Launch the backend**
   ```bash
   python run.py
   ```
   The backend will start on `https://localhost:8000`

2. **Launch the frontend**
   ```bash
   cd app/assistant/agent_flow
   npm start
   ```
   The Visual Flow Editor will be available at `http://localhost:3000`

## Creating Your First Agent System

### Using the Visual Flow Editor

1. **Create a new Manager**
   - Open the Flow Editor at `http://localhost:3000`
   - Click the "+ New Manager" button
   - Enter a name for your manager (e.g., "MyFirstManager")
   - Select "Empty Manager" or a template from the dropdown

2. **Add Agents**
   - Click "+ Add Agent" button at the bottom of the screen
   - Select an agent type (e.g., "Planner", "Researcher", "Writer")
   - Configure the agent's properties in the right sidebar

3. **Connect Agents**
   - Click and drag from one agent's output node to another agent's input node
   - This creates a flow path between agents

4. **Configure Manager Settings**
   - Click on the background to select the manager
   - Adjust global settings in the right sidebar

5. **Save Your Configuration**
   - Click the "💾 Save Manager" button
   - Your configuration is now ready to use

### Example: Simple Question-Answering System

Here's a basic example that processes user questions:

1. **Create these agents:**
   - InputProcessor: Receives and formats user questions
   - Planner: Determines the approach to answer the question
   - Researcher: Gathers information using tools
   - Writer: Formulates the final answer

2. **Connect them in sequence:**
   - InputProcessor → Planner → Researcher → Writer

3. **Test with the API:**
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