# Multi-Agent Managers in EmiAi

**Last Updated:** September 29, 2025

---

## 📚 **Table of Contents**

1. [Overview](#overview)
2. [Core Architecture](#core-architecture)
3. [Key Components](#key-components)
4. [How Managers Work](#how-managers-work)
5. [Manager Lifecycle](#manager-lifecycle)
6. [Multi-Agent Collaboration](#multi-agent-collaboration)
7. [Tool Execution Pattern](#tool-execution-pattern)
8. [Configuration](#configuration)
9. [Examples](#examples)
10. [Best Practices](#best-practices)

---

## 🎯 **Overview**

**Multi-Agent Managers** are the orchestration layer that enables multiple AI agents to collaborate on complex tasks. They provide the infrastructure for:

- ✅ **Agent Coordination** - Routes messages between specialized agents
- ✅ **Shared State** - Manages a blackboard for inter-agent communication
- ✅ **Tool Execution** - Handles tool calling infrastructure
- ✅ **Iteration** - Enables agents to receive tool results and continue
- ✅ **Flow Control** - Manages execution cycles and graceful exits
- ✅ **Error Handling** - Manages failures and recovery

### **Why Managers?**

**Standalone agents cannot iterate** - they process one message and return. Without a manager:
- ❌ Agent calls tool → END (no result received)
- ❌ No way to coordinate multiple agents
- ❌ No shared state between invocations

**With a manager:**
- ✅ Agent calls tool → Manager routes to ToolCaller → Tool executes → Manager routes back to Agent → Agent sees result and continues
- ✅ Multiple agents can collaborate via blackboard
- ✅ Complex workflows with multiple cycles
- ✅ Agents can iterate until task completion

---

## 🏗️ **Core Architecture**

### **Component Diagram:**

```
Multi-Agent Manager
│
├─── Blackboard (Shared State)
│    ├─ state_dict: {task, information, plan, next_agent, ...}
│    └─ messages: [Message, Message, ...]
│
├─── Agent Registry (Agent Instances)
│    ├─ delegator: Routes between agents
│    ├─ planner: Creates strategies
│    ├─ researcher: Gathers information
│    ├─ analyzer: Processes data
│    └─ final_answer: Formats output
│
├─── Tool Registry (Available Tools)
│    ├─ kg_find_node
│    ├─ kg_update_node
│    ├─ ask_user
│    └─ ... other tools
│
├─── Control Nodes (Infrastructure)
│    ├─ ToolCaller: Executes tools
│    ├─ ToolResultHandler: Processes results
│    ├─ ExitNode: Handles completion
│    ├─ FlowExitNode: Manages agent exits
│    └─ ManagerExitNode: Manager completion
│
└─── Flow Config (State Machine)
     └─ state_map: Defines transitions
```

---

## 🧩 **Key Components**

### **1. Blackboard**

The **blackboard** is a shared memory space for agent coordination:

```python
class Blackboard:
    def __init__(self):
        self.state_dict = {
            "task": "",              # Current task description
            "information": "",       # Context and data
            "plan": None,           # Current plan
            "next_agent": None,     # Which agent should act next
            "last_agent": None,     # Which agent just acted
            "exit": False,          # Should we exit?
            "error": False,         # Is there an error?
            "final_answer": None,   # Final result
            "role_bindings": {},    # Agent role mappings
            # ... custom state fields
        }
        self.messages = []          # Message history
```

**Key Features:**
- ✅ **Shared State** - All agents read/write to same state
- ✅ **Message History** - Full communication log
- ✅ **Agent Selection** - Determines next agent to execute
- ✅ **Progress Tracking** - Monitors task completion

**Usage:**
```python
# Agents update state
blackboard.update_state_value('plan', new_plan)
blackboard.update_state_value('next_agent', 'researcher')

# Agents read state
task = blackboard.get_state_value('task')
information = blackboard.get_state_value('information')

# Add messages
blackboard.add_msg(message)
```

---

### **2. Agent Instances**

**Agents** are specialized processors loaded from the agent registry:

```python
# Manager loads agents from config
agents:
  - name: kg_team::planner
    class: Planner
  - name: kg_team::find_node
    class: Planner
  - name: kg_team::delegator
    class: Delegator
```

**Agent Lifecycle:**
1. Agent receives `activation_message`
2. Agent reads blackboard state
3. Agent processes task (may use tools)
4. Agent updates blackboard
5. Agent sets `next_agent` in blackboard
6. Manager routes to next agent

**Agent Pattern:**
```python
class MyAgent:
    def action_handler(self, message: Message):
        # 1. Read blackboard
        task = self.blackboard.get_state_value('task')
        info = self.blackboard.get_state_value('information')
        
        # 2. Make decision
        if need_to_search:
            # Use tool (via blackboard, ToolCaller handles execution)
            self.blackboard.update_state_value('selected_node', 'tool_caller')
            self.blackboard.update_state_value('selected_tool', 'kg_find_node')
        else:
            # Done - set next agent
            self.blackboard.update_state_value('next_agent', 'final_answer')
```

---

### **3. Control Nodes**

**Control nodes** provide infrastructure for tool execution and flow management:

#### **ToolCaller**
- Executes tools based on agent decisions
- Handles tool errors and retries
- Records tool execution

#### **ToolResultHandler**
- Processes tool results
- Updates blackboard with results
- Routes back to calling agent

#### **Exit Nodes**
- **ExitNode**: Normal task completion
- **FlowExitNode**: Agent signals it's done
- **ManagerExitNode**: Manager-level completion

**Flow Pattern:**
```
Agent → "Use kg_find_node tool" → ToolCaller
                                     ↓
                              Tool executes
                                     ↓
                              ToolResultHandler
                                     ↓
Agent ← receives result ←────────────┘
```

---

### **4. Flow Configuration**

The **flow config** defines the state machine for agent transitions:

```yaml
flow_config:
  state_map:
    # Agent routes to tool caller
    "kg_team::planner": "tool_caller"
    
    # Tool caller routes to result handler
    "tool_caller": "tool_result_handler"
    
    # Result handler routes back to agent
    "tool_result_handler": "kg_team::planner"
    
    # Agent can exit flow
    "kg_team::planner_flow_exit_node": "manager_exit_node"
    
    # Other agents
    "kg_team::find_node": "tool_caller"
    "tool_result_handler": "kg_team::find_node"
```

---

## 🔄 **How Managers Work**

### **Execution Flow:**

```
1. Manager receives Message
   ↓
2. Manager resets blackboard
   ↓
3. Manager sets task/information in blackboard
   ↓
4. Manager enters execution loop:
   │
   ├─ Cycle 1:
   │  ├─ Delegator determines next agent
   │  ├─ Agent receives activation message
   │  ├─ Agent processes (may use tools)
   │  ├─ Agent updates blackboard
   │  └─ Agent sets next_agent
   │
   ├─ Cycle 2:
   │  ├─ Delegator determines next agent
   │  ├─ Agent receives activation message
   │  ├─ Agent calls tool via blackboard
   │  ├─ ToolCaller executes tool
   │  ├─ ToolResultHandler processes result
   │  └─ Agent receives result and continues
   │
   ├─ Cycle 3:
   │  ├─ Agent completes task
   │  ├─ Agent sets next_agent = "final_answer"
   │  ├─ FinalAnswer agent formats response
   │  └─ FinalAnswer sets exit = True
   │
   └─ Loop exits (success)
   ↓
5. Manager returns ToolResult with final_answer
```

### **Loop Termination:**

The manager's `_run_loop` exits when:
1. ✅ **Success** - `blackboard['exit'] == True`
2. ⚠️ **Max Cycles** - `cycles > max_cycles`
3. ❌ **Error** - `blackboard['error'] == True`

---

## 🤝 **Multi-Agent Collaboration**

### **Inter-Agent Communication:**

Agents communicate via the **shared blackboard**:

```
Planner Agent:
  ├─ Reads: task, information
  ├─ Decides: "Need to find node X"
  ├─ Writes: next_agent = "find_node"
  │          subtask = "Find node with label 'Wedding'"
  └─ Updates blackboard

Delegator:
  ├─ Reads: next_agent
  └─ Routes to find_node agent

Find_Node Agent:
  ├─ Reads: subtask
  ├─ Uses: kg_find_node tool
  ├─ Receives: search results
  ├─ Writes: next_agent = "planner"
  │          found_node = {...}
  └─ Updates blackboard

Planner Agent (continued):
  ├─ Reads: found_node
  ├─ Decides: "Now update this node"
  ├─ Writes: next_agent = "tool_caller"
  │          selected_tool = "kg_update_node"
  └─ Updates blackboard
```

### **Role Bindings:**

Managers use **role bindings** for flexible agent assignment:

```yaml
role_bindings:
  delegator: kg_team::delegator
  planner: kg_team::planner
  finder: kg_team::find_node
```

**Usage:**
```python
# Agents reference roles, not specific agents
next_agent = "planner"  # References role

# Manager resolves role to actual agent
actual_agent = manager.resolve_role_binding("planner")
# Returns: "kg_team::planner"
```

---

## 🛠️ **Tool Execution Pattern**

### **How Agents Use Tools:**

Agents **do not call tools directly** - they signal the need for a tool via blackboard:

```python
# ❌ WRONG: Direct tool calling
tool = tool_registry.get_tool("kg_find_node")
result = tool.execute(...)

# ✅ CORRECT: Via blackboard + manager infrastructure
self.blackboard.update_state_value('selected_node', 'tool_caller')
self.blackboard.update_state_value('selected_tool', 'kg_find_node')
self.blackboard.update_state_value('tool_arguments', {
    'search_term': 'Wedding',
    'node_type': 'Event'
})
```

### **Tool Execution Cycle:**

```
Agent: "I need to use kg_find_node"
  ├─ Updates blackboard with tool selection
  ├─ Manager sees next_agent changed to "tool_caller"
  └─ Manager activates ToolCaller control node

ToolCaller:
  ├─ Reads selected_tool from blackboard
  ├─ Reads tool_arguments from blackboard
  ├─ Gets tool from tool_registry
  ├─ Executes tool
  ├─ Stores result in blackboard
  └─ Sets next_agent = "tool_result_handler"

ToolResultHandler:
  ├─ Reads tool result from blackboard
  ├─ Formats result for agent
  ├─ Updates blackboard with formatted result
  └─ Sets next_agent = original_calling_agent

Agent: "I received the tool result"
  ├─ Reads tool result from blackboard
  ├─ Processes result
  └─ Continues with task
```

---

## ⚙️ **Configuration**

### **Manager Config Structure:**

```yaml
# app/assistant/multi_agents/kg_team_manager/config.yaml

name: kg_team_manager
class_name: MultiAgentManager
description: "Manager for KG operations using multiple specialized agents"
max_cycles: 50                    # Maximum execution cycles
max_exit_cycles: 10               # Maximum graceful exit cycles

# Role bindings (map roles to specific agents)
role_bindings:
  delegator: kg_team::delegator
  planner: kg_team::planner

# Agent definitions
agents:
  - name: kg_team::delegator
    class: Delegator
  - name: kg_team::planner
    class: Planner
  - name: kg_team::find_node
    class: Planner
  - name: kg_team::final_answer
    class: FinalAnswer

# Available tools
tools:
  allowed_tools:
    - kg_find_node
    - kg_describe_node
    - kg_update_node
    - kg_create_edge
    - ask_user
  except_tools: []

# Control nodes
control_nodes:
  - name: tool_caller
    class: ToolCaller
  - name: tool_result_handler
    class: ToolResultHandler
  - name: exit_node
    class: ExitNode
  - name: flow_exit_node
    class: FlowExitNode
  - name: manager_exit_node
    class: ManagerExitNode

# Flow configuration (state machine)
flow_config:
  state_map:
    "kg_team::planner": "tool_caller"
    "tool_caller": "tool_result_handler"
    "tool_result_handler": "kg_team::planner"
    "kg_team::find_node": "tool_caller"
    "tool_result_handler": "kg_team::find_node"
    "kg_team::planner_flow_exit_node": "manager_exit_node"
```

---

## 💡 **Examples**

### **Example 1: Simple Manager with One Agent**

```yaml
# questioner_manager - asks user a question
name: questioner_manager
class_name: MultiAgentManager
max_cycles: 10

role_bindings:
  questioner: kg_repair_pipeline::questioner::planner

agents:
  - name: kg_repair_pipeline::questioner::planner
    class: Planner

tools:
  allowed_tools: [ask_user]

control_nodes:
  - name: tool_caller
    class: ToolCaller
  - name: tool_result_handler
    class: ToolResultHandler
  - name: manager_exit_node
    class: ManagerExitNode

flow_config:
  state_map:
    "kg_repair_pipeline::questioner::planner": "tool_caller"
    "tool_caller": "tool_result_handler"
    "tool_result_handler": "kg_repair_pipeline::questioner::planner"
    "kg_repair_pipeline::questioner::planner_flow_exit_node": "manager_exit_node"
```

**Usage:**
```python
# Create manager
manager = multi_agent_factory.create_manager("questioner_manager")

# Create message
message = Message(
    data_type="agent_activation",
    sender="KG_Repair_Pipeline",
    receiver="questioner_manager",
    content="What date did the wedding occur?",
    task="Ask user for date",
    information={
        "node_id": "abc-123",
        "problem": "Missing start_date"
    }
)

# Execute
result = manager.run(message)
print(result.content)  # User's response
```

---

### **Example 2: Complex Manager with Multiple Agents**

```yaml
# kg_team_manager - complex KG operations
name: kg_team_manager
class_name: MultiAgentManager
max_cycles: 50

role_bindings:
  delegator: kg_team::delegator
  planner: kg_team::planner

agents:
  - name: kg_team::delegator
    class: Delegator
  - name: kg_team::planner
    class: Planner
  - name: kg_team::find_node
    class: Planner
  - name: kg_team::final_answer
    class: FinalAnswer

tools:
  allowed_tools:
    - kg_find_node
    - kg_describe_node
    - kg_update_node
    - kg_create_node
    - kg_create_edge
    - kg_delete_node

flow_config:
  state_map:
    "kg_team::planner": "tool_caller"
    "kg_team::find_node": "tool_caller"
    "tool_caller": "tool_result_handler"
    "tool_result_handler": "kg_team::planner"
    "kg_team::planner_flow_exit_node": "manager_exit_node"
```

**Execution Flow:**
```
1. Planner: "Need to find node X"
   └─> Sets next_agent = "find_node"

2. Find_Node: Uses kg_find_node tool
   └─> Returns to Planner with results

3. Planner: "Now update the node"
   └─> Uses kg_update_node tool

4. Planner: "Task complete"
   └─> Sets next_agent = "final_answer"

5. Final_Answer: Formats response
   └─> Sets exit = True

6. Manager returns result
```

---

## 🎯 **Best Practices**

### **1. Manager Design**

✅ **DO:**
- Keep managers focused on a specific domain (KG ops, user questions, etc.)
- Use role bindings for flexibility
- Define clear flow_config state transitions
- Set reasonable max_cycles limits
- Include graceful exit handling

❌ **DON'T:**
- Create one giant manager for everything
- Hardcode agent names everywhere
- Forget to define tool_result_handler transitions
- Set max_cycles too low (agents need room to iterate)

### **2. Agent Design**

✅ **DO:**
- Make agents specialized and focused
- Use blackboard for all state
- Update next_agent after processing
- Handle errors gracefully
- Use tools via blackboard, not directly

❌ **DON'T:**
- Try to call tools directly
- Store state in agent instance variables
- Assume specific agent execution order
- Forget to set next_agent

### **3. Tool Usage**

✅ **DO:**
- Wrap low-level functions as agent tools
- Add proper Pydantic schemas
- Include safety checks (especially for destructive operations)
- Return structured results

❌ **DON'T:**
- Call low-level functions directly from agents
- Skip input validation
- Return unstructured data

### **4. Delegation Patterns**

When building complex systems:

```python
# Thin wrapper delegates to manager
class KGImplementer:
    def implement_fixes(self, node, user_response):
        # Create manager
        kg_team = self.multi_agent_factory.create_manager("kg_team_manager")
        
        # Create task
        message = Message(
            data_type="agent_activation",
            content=f"Update node {node.id} with user data",
            task="Apply KG modifications",
            information={"node": node, "updates": user_response}
        )
        
        # Delegate
        result = kg_team.run(message)
        return result
```

---

## 🔗 **Related Documentation**

- **Blackboard System**: `docs/guides/blackboard_system.md`
- **Creating First Agent**: `docs/guides/creating_first_agent.md`
- **Daily Summary Manager**: `docs/daily_summary_manager.md` (complex example)
- **KG Repair Pipeline**: `docs/knowledge_graph/KG_PIPELINE_DETAILS.md` (usage in pipelines)

---

## 📝 **Summary**

**Multi-Agent Managers are orchestration platforms** that provide:

1. ✅ **Iteration Infrastructure** - Agents can receive tool results and continue
2. ✅ **Multi-Agent Collaboration** - Multiple agents work together via blackboard
3. ✅ **Tool Execution** - ToolCaller/ToolResultHandler handle tool usage
4. ✅ **Flow Management** - State machine controls execution flow
5. ✅ **Shared State** - Blackboard enables coordination
6. ✅ **Error Handling** - Graceful exits and recovery

**Key Insight:** Managers aren't just "tool wrappers" - they're complete collaboration platforms that enable complex, iterative, multi-agent workflows!

---

**Last Updated:** September 29, 2025  
**Version:** 1.0  
**Maintainer:** EmiAi Team
