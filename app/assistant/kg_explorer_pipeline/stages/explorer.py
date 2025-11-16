"""
KG Explorer Stage

This stage performs the actual exploration of selected nodes to discover
relationships and perform temporal reasoning using individual agents.
"""

import time
from typing import List, Dict, Any, Optional
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger
from app.assistant.kg_explorer_pipeline.data_models.exploration_node import ExplorationNode
from app.assistant.kg_explorer_pipeline.data_models.exploration_result import ExplorationResult, Discovery, TemporalInference, MissingConnection

logger = get_logger(__name__)


class KGExplorer:
    """
    Explores nodes to discover relationships and perform temporal reasoning.
    Uses individual agents like the repair pipeline does.
    """
    
    def __init__(self):
        self.multi_agent_factory = DI.multi_agent_manager_factory
        
    def explore_node(self, node: ExplorationNode, exploration_config: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Explore a single node to discover relationships and perform temporal reasoning.
        
        Args:
            node: The node to explore
            exploration_config: Configuration for exploration focus
            
        Returns:
            Dict with actionable_recommendations from kg_explorer_relationship_manager
        """
        print(f"🧠 [DEBUG] Exploring node: {node.label}")
        logger.info(f"🧠 Exploring node: {node.label}")
        start_time = time.time()
        
        try:
            # Delegate to kg_explorer_manager for actual exploration
            print(f"🧠 [DEBUG] Delegating to kg_explorer_manager for node {node.label}")
            return self._delegate_to_kg_explorer_manager(node, exploration_config, time.time() - start_time)
            
        except Exception as e:
            print(f"❌ [DEBUG] Failed to explore node {node.label}: {e}")
            logger.error(f"❌ Failed to explore node {node.label}: {e}")
            return {
                "error": str(e),
                "exploration_summary": f"Failed to explore {node.label}",
                "actionable_recommendations": []
            }
    
    def _delegate_to_kg_explorer_manager(self, node: ExplorationNode, exploration_config: Optional[Dict], exploration_time: float) -> Dict[str, Any]:
        """
        Delegate actual exploration to kg_explorer_manager.
        
        Args:
            node: The node to explore
            exploration_config: Configuration for exploration
            exploration_time: Time spent so far
            
        Returns:
            ExplorationResult with discoveries and inferences
        """
        try:
            # Create task for kg_explorer_relationship_manager
            task = f"Explore node {node.label} to discover implicit relationships through multi-hop semantic reasoning"
            information = f"Node ID: {node.id}, Type: {node.type}, Category: {node.category}, Description: {node.description or 'None'}"
            
            print(f"🧠 [DEBUG] Creating kg_explorer_manager for node {node.id}")
            print(f"🧠 [DEBUG] Task: {task}")
            
            # Create kg_explorer_relationship_manager instance for entity relationship discovery
            kg_explorer_manager = self.multi_agent_factory.create_manager("kg_explorer_relationship_manager")
            
            # Create message for kg_explorer_relationship_manager
            import json
            information_dict = {
                "node_id": node.id,
                "node_label": node.label,
                "node_type": node.type,
                "node_category": node.category,
                "node_description": node.description,
                "exploration_mode": "relationship_discovery",
                "instructions": [
                    f"Find all direct relationships of {node.label}",
                    "For each connected entity, explore their relationships",
                    "Look for transitive relationship patterns",
                    "Identify missing edges that should exist",
                    "Focus on family/work/location relationship chains"
                ],
                "source": "kg_explorer_pipeline"
            }
            
            message = Message(
                data_type="agent_activation",
                sender="KG_Explorer_Pipeline",
                receiver="kg_explorer_manager",
                content=task,
                task=task,
                information=json.dumps(information_dict)
            )
            
            # Execute kg_explorer_manager (same as repair pipeline)
            print(f"🧠 [DEBUG] Executing kg_explorer_manager...")
            result = kg_explorer_manager.request_handler(message)
            
            print(f"🧠 [DEBUG] kg_explorer_manager result: {result.content[:100] if result.content else 'No content'}...")
            
            # Extract final_answer dict from manager result (no conversion needed)
            exploration_result = self._convert_manager_result_to_exploration_result(node, result, exploration_time)
            
            # exploration_result is now a dict with actionable_recommendations
            recommendations = exploration_result.get('actionable_recommendations', []) if isinstance(exploration_result, dict) else []
            print(f"✅ [DEBUG] Explored {node.label}: {len(recommendations)} actionable recommendations")
            logger.info(f"✅ Explored {node.label}: {len(recommendations)} actionable recommendations")
            
            return exploration_result
            
        except Exception as e:
            print(f"❌ [DEBUG] kg_explorer_manager delegation failed: {e}")
            logger.error(f"❌ kg_explorer_manager delegation failed: {e}")
            return {
                "error": str(e),
                "exploration_summary": f"Failed to explore {node.label}",
                "actionable_recommendations": []
            }
    
    def _convert_manager_result_to_exploration_result(self, node: ExplorationNode, manager_result, exploration_time: float):
        """
        Extract the final_answer from manager result.
        No conversion needed - just pass through the structured actionable_recommendations as a dict.
        Downstream repair managers can read the JSON and understand what to do.
        """
        try:
            if not manager_result:
                print(f"🧠 [DEBUG] Manager returned no result")
                return {"error": "No result from manager", "actionable_recommendations": []}
            
            # The manager's final_answer is in the data field
            final_answer = manager_result.data if hasattr(manager_result, 'data') else None
            
            if not final_answer:
                print(f"🧠 [DEBUG] Manager result has no data field")
                return {"error": "No data from manager", "actionable_recommendations": []}
            
            print(f"🧠 [DEBUG] Manager returned final_answer with keys: {list(final_answer.keys()) if isinstance(final_answer, dict) else 'not a dict'}")
            
            # Extract actionable_recommendations and summary - pass through as-is
            actionable_recommendations = final_answer.get('actionable_recommendations', [])
            exploration_summary = final_answer.get('exploration_summary', '')
            
            print(f"🧠 [DEBUG] Found {len(actionable_recommendations)} actionable recommendations")
            print(f"🧠 [DEBUG] Exploration summary: {exploration_summary[:100] if exploration_summary else 'No summary'}...")
            
            # Return the complete final_answer dict - no conversion needed
            # The structured recommendations are ready to be consumed by repair agents
            return final_answer
            
        except Exception as e:
            print(f"❌ [DEBUG] Failed to extract manager result: {e}")
            import traceback
            print(f"❌ [DEBUG] Traceback: {traceback.format_exc()}")
            return {"error": str(e), "actionable_recommendations": []}