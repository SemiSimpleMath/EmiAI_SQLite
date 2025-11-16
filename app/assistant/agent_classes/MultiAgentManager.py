"""
MultiAgentManager class for managing multiple agents in a coordinated workflow.
"""

from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class MultiAgentManager(Agent):
    """
    A manager that coordinates multiple agents to work together on complex tasks.
    """
    
    def __init__(self, name: str, blackboard, config: dict = None, agent_registry=None):
        super().__init__(name, blackboard, config, agent_registry)
        self.agents = {}
        self.flow_config = config.get('flow_config', {}) if config else {}
        self.max_cycles = config.get('max_cycles', 50) if config else 50
        self.cycle_count = 0
        
    def add_agent(self, agent_name: str, agent_instance):
        """Add an agent to the manager."""
        self.agents[agent_name] = agent_instance
        logger.info(f"Added agent {agent_name} to manager {self.name}")
    
    def execute_flow(self, message: Message) -> Message:
        """
        Execute the multi-agent flow.
        
        Args:
            message: Input message to process
            
        Returns:
            Message: Final result from the flow
        """
        logger.info(f"Starting multi-agent flow for {self.name}")
        
        try:
            # Initialize flow state
            current_agent = self.flow_config.get('initial_agent', 'delegator')
            self.cycle_count = 0
            
            # Execute flow cycles
            while self.cycle_count < self.max_cycles:
                self.cycle_count += 1
                logger.info(f"Flow cycle {self.cycle_count}/{self.max_cycles}, current agent: {current_agent}")
                
                # Get current agent
                if current_agent not in self.agents:
                    logger.error(f"Agent {current_agent} not found in manager {self.name}")
                    break
                
                agent = self.agents[current_agent]
                
                # Execute agent
                result = agent.process_message(message)
                
                # Check for flow exit conditions
                if hasattr(result, 'action') and result.action == 'flow_exit_node':
                    logger.info(f"Flow exit requested by {current_agent}")
                    break
                
                # Determine next agent
                next_agent = self._get_next_agent(current_agent, result)
                if next_agent is None:
                    logger.info(f"No next agent determined, ending flow")
                    break
                
                current_agent = next_agent
                message = result  # Pass result as next message
            
            logger.info(f"Multi-agent flow completed after {self.cycle_count} cycles")
            return result
            
        except Exception as e:
            logger.error(f"Multi-agent flow failed: {e}")
            return Message(
                content=f"Flow execution failed: {str(e)}",
                task="error",
                data={"error": str(e)}
            )
    
    def _get_next_agent(self, current_agent: str, result) -> str:
        """Determine the next agent based on flow configuration."""
        state_map = self.flow_config.get('state_map', {})
        
        # Check if current agent has a specific next agent
        if current_agent in state_map:
            return state_map[current_agent]
        
        # Default flow logic
        if hasattr(result, 'action'):
            if result.action == 'tool_caller':
                return 'tool_result_handler'
            elif result.action == 'flow_exit_node':
                return None
        
        # Default to delegator if no specific mapping
        return 'delegator'
    
    def process_message(self, message: Message) -> Message:
        """
        Process a message through the multi-agent flow.
        
        Args:
            message: Input message
            
        Returns:
            Message: Processed result
        """
        return self.execute_flow(message)
