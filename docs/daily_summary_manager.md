# Daily Summary Manager

## Overview

The Daily Summary Manager is a comprehensive multi-agent system designed to create detailed daily summaries that help users understand their day ahead, important events, tasks, and relevant information. It leverages your existing infrastructure including calendar tools, todo management, web scraping, and scheduling optimization.

## Features

### 🗓️ **Calendar Analysis**
- Fetches calendar events for the entire week
- Identifies important upcoming events (family time, meetings, special occasions)
- Analyzes schedule patterns and potential conflicts
- Highlights free time and busy periods
- **Flags upcoming important events** (anniversaries, birthdays, deadlines) that need advance notice

### 📋 **Todo Task Analysis**
- Retrieves and prioritizes todo tasks
- Suggests optimal timing for task completion
- Identifies task dependencies and urgency
- Provides task management recommendations

### 📧 **Email Analysis**
- Analyzes overnight emails for important messages
- Identifies urgent communications requiring immediate attention
- Prioritizes emails by importance and action required
- Provides email insights and patterns

### 🌐 **Web Information Gathering**
- Collects relevant news and weather information
- Scrapes favorite websites for updates
- Gathers information that impacts daily planning
- Provides context for decision-making

### ⏰ **Schedule Optimization**
- Creates optimized daily schedules
- Recommends optimal timing for activities
- Suggests meal times and breaks
- Balances productivity with personal needs

### 📊 **Comprehensive Summary**
- Synthesizes all information into actionable summaries
- Provides daily overview (e.g., "It's family zoom day")
- Highlights key events and priority tasks
- Offers clear next steps and recommendations

## Architecture

The Daily Summary Manager follows the same architecture as your `emi_team_manager` with specialized agents for different aspects of daily planning:

### **Agent Team Structure**

1. **Delegator** (`daily_summary::delegator`)
   - Coordinates workflow between specialized agents
   - Determines which agent should act next
   - Manages the overall execution flow

2. **Planner** (`daily_summary::planner`)
   - Creates the overall strategy for gathering daily information
   - Determines what information is needed and in what order
   - Delegates to specialized agents

3. **Calendar Analyzer** (`daily_summary::calendar_analyzer`)
   - Specializes in analyzing calendar events
   - Identifies important upcoming events
   - Provides schedule insights and patterns

4. **Todo Analyzer** (`daily_summary::todo_analyzer`)
    - Analyzes and prioritizes todo tasks
    - Suggests optimal timing for task completion
    - Identifies task dependencies and urgency

5. **Email Analyzer** (`daily_summary::email_analyzer`)
    - Analyzes overnight emails for important messages
    - Identifies urgent communications requiring attention
    - Prioritizes emails by importance and action required

6. **Web Gatherer** (`daily_summary::web_gatherer`)
   - Gathers relevant information from favorite websites
   - Collects news, weather, and other relevant updates
   - Provides context for daily decision-making

7. **Schedule Optimizer** (`daily_summary::schedule_optimizer`)
    - Creates optimized daily schedules
    - Recommends timing for activities, meals, and breaks
    - Balances productivity with personal needs

8. **Final Summary** (`daily_summary::final_summary`)
   - Synthesizes all information into comprehensive summaries
   - Creates actionable daily overviews
   - Provides clear next steps and recommendations

### **Control Nodes**

- **ToolCaller**: Executes tools and agents based on planner decisions
- **ToolResultHandler**: Processes and stores tool execution results
- **ExitNode**: Handles graceful termination
- **GracefulExitControlNode**: Manages error conditions

## Usage

### **As a Tool**

The Daily Summary Manager can be called as a tool from other managers:

```python
# Add to allowed_tools in manager config
allowed_tools:
  - daily_summary_manager

# Call with arguments
tool_arguments = {
    "task": "Create a comprehensive daily summary",
    "information": "Focus on today's schedule and important events this week"
}
```

### **Direct Manager Creation**

```python
from app.assistant.ServiceLocator.service_locator import DI

# Create manager instance
manager_factory = DI.multi_agent_manager_factory
daily_summary_manager = manager_factory.create_manager('daily_summary_manager', name='my_daily_summary')

# Create request message
message = Message(
    event_topic="task_request",
    sender="user",
    content="Create my daily summary",
    task="Create a comprehensive daily summary",
    information="Focus on today's priorities"
)

# Process request
result = daily_summary_manager.request_handler(message)
print(result.content)
```

## Configuration

### **Manager Configuration**

The manager configuration is located at `app/assistant/multi_agents/daily_summary_manager/config.yaml`:

```yaml
name: daily_summary_manager
class_name: MultiAgentManager
description: "A manager that creates comprehensive daily summaries"
max_cycles: 50
role_bindings:
  delegator: daily_summary::delegator

agents:
  - name: daily_summary::delegator
    class: Delegator
  - name: daily_summary::planner
    class: Planner
  # ... other agents

tools:
  allowed_tools:
    - get_calendar_events
    - get_todo_tasks
    - search_web
    - scrape_url
    - rag_query
    # ... other tools
```

### **Agent Configurations**

Each specialized agent has its own configuration:

- **Calendar Analyzer**: `app/assistant/agents/daily_summary/calendar_analyzer/config.yaml`
- **Todo Analyzer**: `app/assistant/agents/daily_summary/todo_analyzer/config.yaml`
- **Email Analyzer**: `app/assistant/agents/daily_summary/email_analyzer/config.yaml`
- **Web Gatherer**: `app/assistant/agents/daily_summary/web_gatherer/config.yaml`
- **Schedule Optimizer**: `app/assistant/agents/daily_summary/schedule_optimizer/config.yaml`
- **Final Summary**: `app/assistant/agents/daily_summary/final_summary/config.yaml`

## Integration with Existing Tools

The Daily Summary Manager leverages your existing tool infrastructure:

### **Calendar Tools**
- `get_calendar_events`: Fetches calendar events for analysis
- `create_calendar_event`: Can create new events if needed
- `update_calendar_event`: Can modify existing events

### **Todo Tools**
- `get_todo_tasks`: Retrieves todo tasks for analysis
- `create_todo_task`: Can create new tasks
- `update_todo_task`: Can modify existing tasks

### **Email Tools**
- `get_email`: Retrieves overnight emails for analysis
- `send_email`: Can send email responses if needed

### **Web Tools**
- `search_web`: Searches for relevant information
- `scrape_url`: Scrapes specific websites
- `rag_query`: Queries knowledge base for relevant information

### **Manager Tools**
- `web_manager`: Can delegate web-related tasks
- `event_manager`: Can delegate event management tasks

## Example Output

The Daily Summary Manager produces comprehensive summaries like:

```
📅 Daily Summary - Monday, January 15, 2024

🎯 **Daily Overview**: It's family zoom day! You have an important family call at 7pm.

📅 **Key Events Today**:
- 9:00 AM: Team Standup Meeting
- 2:00 PM: Project Review (Important - prepare presentation)
- 7:00 PM: Family Zoom Call (30 min)
- 8:30 PM: Evening Planning Session

📋 **Priority Tasks**:
- High Priority: Prepare project presentation slides (due 2pm)
- Medium Priority: Review quarterly reports
- Quick Wins: Respond to 3 pending emails

📧 **Important Emails**:
- High Priority: Urgent project update from boss (requires immediate response)
- Medium Priority: Meeting confirmation for tomorrow's client call
- Low Priority: Newsletter from industry publication (informational)

⏰ **Schedule Recommendations**:
- 8:30-9:00 AM: Prepare for standup meeting
- 9:00-9:30 AM: Team standup
- 9:30-11:00 AM: Deep work on project presentation
- 11:00-11:15 AM: Break
- 11:15-12:30 PM: Continue presentation work
- 12:30-1:30 PM: Lunch break
- 1:30-2:00 PM: Final presentation prep
- 2:00-3:00 PM: Project review meeting
- 3:00-5:00 PM: Review quarterly reports
- 5:00-6:30 PM: Free time / flexible tasks
- 6:30-7:00 PM: Prepare for family call
- 7:00-7:30 PM: Family zoom call
- 8:30-9:00 PM: Evening planning

📅 **Upcoming Important Events**:
- Anniversary next week (7 days) - Consider gift planning
- Birthday party this weekend (3 days) - Need to buy gift
- Project deadline next Friday (5 days) - Start preparation

🌤️ **Relevant Information**:
- Weather: Sunny, 72°F - great day for a lunch walk
- News: Major tech announcement at 3pm (relevant to your industry)
- Traffic: Normal commute conditions

✅ **Action Items**:
1. Start presentation prep immediately (high priority)
2. Respond to urgent project update email from boss
3. Block 2-3pm for project review meeting
4. Set reminder for family call at 6:45pm
5. Plan anniversary gift (upcoming event)
6. Check tech news at 3pm for industry updates
```

## Customization

### **Adding New Information Sources**

To add new information sources, you can:

1. **Add new tools** to the `allowed_tools` list in the manager config
2. **Create new specialized agents** for specific types of information
3. **Modify existing agents** to handle new data types

### **Customizing Agent Behavior**

Each agent can be customized by:

1. **Modifying prompts** in the `prompts/` directories
2. **Adjusting agent forms** to capture different information
3. **Adding new tools** to specific agents
4. **Customizing the workflow** in the delegator

### **Integrating with Other Managers**

The Daily Summary Manager can be integrated with other managers:

```yaml
# In emi_team_manager config
tools:
  allowed_tools:
    - daily_summary_manager
    # ... other tools
```

## Testing

Use the provided test script to verify functionality:

```bash
python test_daily_summary_manager.py
```

## Future Enhancements

Potential improvements and extensions:

1. **Machine Learning Integration**: Use ML to learn user preferences and patterns
2. **Predictive Scheduling**: Predict optimal times for different types of tasks
3. **Integration with More Services**: Add support for more calendar and todo services
4. **Personalization**: Learn from user feedback to improve recommendations
5. **Real-time Updates**: Provide real-time updates as the day progresses

## Troubleshooting

### **Common Issues**

1. **Manager Not Found**: Ensure the manager is properly registered in the manager registry
2. **Tool Errors**: Check that all required tools are available and properly configured
3. **Agent Failures**: Verify that all agent configurations and prompts are correct
4. **Permission Issues**: Ensure proper access to calendar and todo services

### **Debugging**

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('app.assistant').setLevel(logging.DEBUG)
```

## Conclusion

The Daily Summary Manager provides a comprehensive solution for daily planning and information synthesis. It leverages your existing infrastructure while adding specialized intelligence for daily summary creation. The modular design allows for easy customization and extension to meet specific needs.
