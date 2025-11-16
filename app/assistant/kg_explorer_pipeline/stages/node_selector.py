"""
KG Node Selector Stage

This stage selects the most promising nodes for exploration using an agent.
Follows the same pattern as the repair pipeline analyzer.
"""

from typing import List, Dict, Any, Optional
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger
from app.assistant.kg_explorer_pipeline.data_models.exploration_node import ExplorationNode

logger = get_logger(__name__)


class KGNodeSelector:
    """
    Selects the most promising nodes for exploration.
    Uses an agent to analyze candidate nodes and select the best ones.
    """
    
    def __init__(self):
        self.agent_name = "kg_explorer::node_selector"
        
    def select_nodes(self, candidate_nodes: List[Dict[str, Any]], max_nodes: int = 3) -> List[ExplorationNode]:
        """
        Select the most promising nodes for exploration.
        
        Args:
            candidate_nodes: List of candidate nodes from the database
            max_nodes: Maximum number of nodes to select
            
        Returns:
            List of selected ExplorationNode objects
        """
        try:
            print(f"🔍 [DEBUG] Selecting nodes from {len(candidate_nodes)} candidates (max={max_nodes})")
            logger.info(f"🔍 Selecting nodes from {len(candidate_nodes)} candidates (max={max_nodes})")
            
            if not candidate_nodes:
                print(f"⚠️ [DEBUG] No candidate nodes provided")
                logger.warning("⚠️ No candidate nodes provided")
                return []
            
            # Create selection task
            task = f"Select the most promising nodes for exploration from {len(candidate_nodes)} candidates. Focus on nodes with exploration potential for relationship discovery and temporal reasoning."
            
            # Prepare agent input data (concatenate multiple nodes as string)
            import json
            
            # Format candidate nodes as concatenated string (limit to first 10 for prompt)
            candidate_nodes_text = ""
            for i, node in enumerate(candidate_nodes[:10]):
                candidate_nodes_text += f"Node {i+1}:\n"
                candidate_nodes_text += f"  ID: {node.get('id', '')}\n"
                candidate_nodes_text += f"  Label: {node.get('label', '')}\n"
                candidate_nodes_text += f"  Type: {node.get('type', '')}\n"
                candidate_nodes_text += f"  Category: {node.get('category', '')}\n"
                candidate_nodes_text += f"  Description: {node.get('description', 'No description')}\n"
                candidate_nodes_text += f"  Start Date: {node.get('start_date', 'Not specified')}\n"
                candidate_nodes_text += f"  End Date: {node.get('end_date', 'Not specified')}\n"
                candidate_nodes_text += f"  Connection Count: {node.get('connection_count', 0)}\n\n"
            
            # Create agent input with concatenated string (same as repair pipeline)
            agent_input = {
                "candidate_nodes": candidate_nodes_text,
                "max_nodes": str(max_nodes),
                "total_candidates": str(len(candidate_nodes))
            }
            
            # Create message for the node selector agent (same as repair pipeline)
            message = Message(agent_input=agent_input)
            
            # Get the node selector agent
            selector_agent = DI.agent_factory.create_agent(self.agent_name)
            
            # Process the message
            print(f"🔍 [DEBUG] Calling node selector agent: {self.agent_name}")
            result = selector_agent.action_handler(message)
            
            if not result:
                print(f"⚠️ [DEBUG] Node selector returned no results")
                logger.warning("⚠️ Node selector returned no results")
                return []
            
            print(f"🔍 [DEBUG] Node selector result: {result.content[:100] if result.content else 'No content'}...")
            
            # Parse the agent's output to get selected nodes
            selected_nodes = self._parse_selection_results(result, candidate_nodes)
            
            print(f"✅ [DEBUG] Selected {len(selected_nodes)} nodes for exploration")
            logger.info(f"✅ Selected {len(selected_nodes)} nodes for exploration")
            
            return selected_nodes
            
        except Exception as e:
            print(f"❌ [DEBUG] Failed to select nodes: {e}")
            logger.error(f"❌ Failed to select nodes: {e}")
            return []
    
    def _parse_selection_results(self, agent_result, candidate_nodes: List[Dict[str, Any]]) -> List[ExplorationNode]:
        """
        Parse the node selector's output to extract selected nodes.
        
        Args:
            agent_result: The result from the node selector agent
            candidate_nodes: List of candidate nodes to match against
            
        Returns:
            List of selected ExplorationNode objects
        """
        selected_nodes = []
        
        try:
            # Get the agent's structured output
            if hasattr(agent_result, 'data') and agent_result.data:
                selection_data = agent_result.data
            else:
                # Try to parse from content if no structured data
                content = agent_result.content if agent_result.content else ""
                print(f"🔍 [DEBUG] Parsing from content: {content[:200]}...")
                
                # For now, select the first few nodes as a fallback
                # In a real implementation, you'd parse the agent's output
                selection_data = {
                    'selected_nodes': [
                        {'node_id': node['id'], 'selection_reason': 'Fallback selection'} 
                        for node in candidate_nodes[:3]
                    ]
                }
            
            # Extract selected nodes
            if 'selected_nodes' in selection_data:
                for selection in selection_data['selected_nodes']:
                    node_id = selection.get('node_id')
                    if node_id:
                        # Find the corresponding candidate node
                        candidate = next((n for n in candidate_nodes if str(n['id']) == str(node_id)), None)
                        if candidate:
                            selected_nodes.append(ExplorationNode(
                                id=candidate['id'],
                                label=candidate['label'],
                                semantic_label=candidate.get('semantic_label'),
                                type=candidate['type'],
                                category=candidate['category'],
                                description=candidate.get('description'),
                                start_date=candidate.get('start_date').isoformat() if candidate.get('start_date') else None,
                                end_date=candidate.get('end_date').isoformat() if candidate.get('end_date') else None,
                                connection_count=candidate.get('connection_count', 0)
                            ))
            
            # If no structured selection, fall back to first few candidates
            if not selected_nodes:
                print(f"🔍 [DEBUG] No structured selection found, using fallback")
                for candidate in candidate_nodes[:3]:
                    selected_nodes.append(ExplorationNode(
                        id=candidate['id'],
                        label=candidate['label'],
                        semantic_label=candidate.get('semantic_label'),
                        type=candidate['type'],
                        category=candidate['category'],
                        description=candidate.get('description'),
                        start_date=candidate.get('start_date').isoformat() if candidate.get('start_date') else None,
                        end_date=candidate.get('end_date').isoformat() if candidate.get('end_date') else None,
                        connection_count=candidate.get('connection_count', 0)
                    ))
            
        except Exception as e:
            print(f"❌ [DEBUG] Error parsing selection results: {e}")
            logger.error(f"❌ Error parsing selection results: {e}")
            
            # Fallback to first few candidates
            for candidate in candidate_nodes[:3]:
                selected_nodes.append(ExplorationNode(
                    id=candidate['id'],
                    label=candidate['label'],
                    semantic_label=candidate.get('semantic_label'),
                    type=candidate['type'],
                    category=candidate['category'],
                    description=candidate.get('description'),
                    start_date=candidate.get('start_date'),
                    end_date=candidate.get('end_date'),
                    connection_count=candidate.get('connection_count', 0)
                ))
        
        return selected_nodes