# Using the Flow Editor

The Flow Editor is EmiAi's visual interface for designing and configuring agent systems. This tutorial will guide you through using this powerful tool.

## Accessing the Flow Editor

1. Ensure your backend is running:
   ```bash
   python run.py
   ```

2. Start the frontend:
   ```bash
   cd app/assistant/agent_flow
   npm start
   ```

3. Open your browser to `http://localhost:3000`

## Interface Overview

![Flow Editor Interface](../images/flow_editor.png)

The Flow Editor has several key areas:
- **Canvas**: The main area where you design your agent flow
- **Toolbar**: Contains buttons for adding nodes and saving
- **Manager Selector**: Dropdown to select the current manager
- **Properties Panel**: Right sidebar for configuring selected items
- **Node Library**: Bottom panel showing available agent types

## Creating a New Manager

1. Click the "Current Manager" dropdown
2. Select "+ New Manager"
3. In the dialog that appears:
   - Enter a name for your manager
   - Optionally select a template as a starting point
   - Click "Create"

## Adding Agents to Your Flow

1. Click the "+ Add Agent" button at the bottom of the screen
2. Select an agent type from the list that appears
3. The agent will be added to your canvas
4. Drag to position it where you want

## Configuring Agent Properties

1. Click on an agent node to select it
2. The Properties Panel on the right will show its configuration
3. Edit the properties:
   - **Name**: Unique identifier for the agent
   - **Type**: The agent's implementation class
   - **Description**: Optional explanation of the agent's purpose
   - **Additional properties**: Vary by agent type

## Connecting Agents

1. Hover over an agent node to see its connection points
2. Click and drag from an output handle to another agent's input handle
3. Release to create a connection
4. The connection represents message flow between agents

## Managing Flow Logic

There are several ways to control flow between agents:

### Direct Connections
Simple connections mean "always go to this agent next"

### Conditional Routing
Some agents can determine the next agent dynamically:

```python
# In your agent code
next_agent = "researcher" if needs_research else "writer"
self.blackboard.update_state_value("next_agent", next_agent)
```

### State-Based Flow
The "state_map" in your manager configuration can define rules:

```yaml
flow_config:
  state_map:
    input_agent: planner
    planner:
      condition: "task.type == 'research'"
      true: researcher
      false: writer
    researcher: writer
    writer: output_agent
```

## Saving Your Configuration

1. Click the "💾 Save Manager" button at the bottom left
2. Your configuration will be saved to the server
3. You'll see a confirmation message

## Testing Your Flow

To test your flow directly from the editor:

1. Click "Test" in the toolbar
2. Enter a test message in the input field
3. Click "Run"
4. Watch the execution flow through your agents
5. View the results in the output panel

## Managing Templates

Templates are pre-configured flows you can reuse:

1. **Creating a template**:
   - Build and save a manager
   - Click "Save as Template" 
   - Enter a template name and description

2. **Using a template**:
   - When creating a new manager, select your template
   - The new manager will be a copy of the template

## Advanced Features

### Context Menu
Right-click on nodes or the canvas for additional options:
- Delete node
- Duplicate node
- Clear all
- Export configuration

### Layout Tools
- **Auto Layout**: Automatically arranges nodes
- **Zoom**: Use the mouse wheel to zoom in/out
- **Pan**: Click and drag the canvas to reposition

### Importing and Exporting
- **Export**: Save your configuration as a JSON file
- **Import**: Load a configuration from a file

## Troubleshooting

Common issues:
- **Connections not working**: Ensure agents are properly configuring "next_agent"
- **Agents not appearing**: Check the agent registry for registration issues
- **Changes not saving**: Verify backend server is running

## Next Steps

- Learn about [Custom Tools](./custom_tools.md)
- Explore advanced [Agent Patterns](../guides/agent_patterns.md)
- Understand [Blackboard System](../guides/blackboard_system.md) detailseating First Agent](../tutorials/creating_first_agent.md) tutorial
- Learn about the visual editor in [Using Flow Editor](../tutorials/using_flow_editor.md)
- Explore how to create custom tools in [Custom Tools](../tutorials/custom_tools.md) 