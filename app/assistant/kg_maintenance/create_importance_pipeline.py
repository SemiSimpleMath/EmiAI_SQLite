"""
Create Importance Pipeline
Calculates global importance for each node in the knowledge graph
"""

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node
from app.assistant.kg_core.kg_tools import inspect_node_neighborhood
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 20  # Process edges in batches like description creator


def calculate_automatic_importance(edge_count: int, node_type: str) -> tuple[float, str]:
    """
    Calculate automatic importance based on edge count rules
    Returns (importance_score, rule_applied)
    """
    if edge_count > 50:
        return 1.0, ">50 edges = 1.0"
    elif edge_count > 20:
        return 0.9, ">20 edges = 0.9"
    elif edge_count > 10:
        base_importance = 0.8
        # Add 0.5 bonus for persons with >10 edges
        if "person" in node_type.lower():
            return min(1.0, base_importance + 0.5), ">10 edges = 0.8 + 0.5 person bonus"
        else:
            return base_importance, ">10 edges = 0.8"
    else:
        return None, None


def run_importance_pipeline(skip_high_edge_nodes: bool = True):
    """
    Main pipeline function to calculate importance for all nodes
    """
    session = get_session()
    importance_agent = DI.agent_factory.create_agent("kg_maintenance::create_importance")
    
    # Get all nodes
    all_nodes = session.query(Node).all()
    logger.info(f"Processing {len(all_nodes)} nodes for importance calculation")
    
    processed_count = 0
    error_count = 0
    automatic_count = 0
    
    for node in all_nodes:
        # Skip nodes with label "Jukka" (hardcoded for now)
        if node.label == "Jukka":
            logger.info(f"Skipping node: {node.label} (hardcoded skip)")
            continue
            
        logger.info(f"Processing node: {node.label} ({node.id})")
        
        try:
            # Get node neighborhood data using existing tool
            node_info, all_edges = inspect_node_neighborhood(node.id, session)
            edge_count = len(all_edges)
            
            # Check for automatic importance assignment
            automatic_importance, rule_applied = calculate_automatic_importance(edge_count, node_info.get('type', ''))
            
            if automatic_importance is not None and skip_high_edge_nodes:
                # Automatically assign importance
                logger.info(f" - Automatically assigning importance {automatic_importance} to {node.label} ({rule_applied})")
                update_node_importance(session, node.id, automatic_importance, rule_applied)
                automatic_count += 1
                continue
            
            logger.info(f" - Processing {edge_count} relationships for {node.label}")
            
            # Format neighborhood data as string for blackboard injection
            neighborhood_text = []
            for i, rel in enumerate(all_edges, 1):
                rel_text = f"{i}. {rel['direction'].title()} relationship: {rel['edge_type']}\n"
                rel_text += f"   - Connected to: {rel['connected_node']['label']} ({rel['connected_node']['type']})"
                if rel['connected_node'].get('description'):
                    desc = rel['connected_node']['description'][:100]
                    if len(rel['connected_node']['description']) > 100:
                        desc += "..."
                    rel_text += f"\n   - Description: {desc}"
                neighborhood_text.append(rel_text)
            
            neighborhood_data = f"Total relationships: {edge_count}\n" + "\n".join(neighborhood_text)
            
            # Get current importance from node attributes
            current_importance = node.attributes.get('importance', 0.0) if node.attributes else 0.0
            
            # Prepare data for the agent
            agent_input = {
                "node_label": node_info.get('label', ''),
                "node_type": node_info.get('type', ''),
                "node_aliases": ", ".join(node_info.get('aliases', [])),
                "node_attributes": str(node.attributes) if node.attributes else "{}",
                "neighborhood_data": neighborhood_data,
                "current_importance": str(current_importance),
                "edge_count": str(edge_count)
            }
            
            # Call the agent
            response = importance_agent.action_handler(Message(agent_input=agent_input))
            
            if response and response.data:
                importance_result = response.data
                logger.info(f" - Generated importance {importance_result.get('importance_score', 0)} for {node.label}")
                
                # Update node importance
                update_node_importance(
                    session, 
                    node.id, 
                    importance_result.get('importance_score', 0.0),
                    importance_result.get('reasoning', ''),
                    importance_result.get('confidence', 0.0)
                )
                processed_count += 1
            else:
                error_count += 1
                logger.error(f" - Failed to generate importance for {node.label}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing node {node.label}: {e}")
            session.rollback()
    
    logger.info(f"Pipeline completed: {processed_count} processed, {automatic_count} automatic, {error_count} errors")
    return {"processed": processed_count, "automatic": automatic_count, "errors": error_count}


def update_node_importance(session: Session, node_id: str, importance: float, reasoning: str = "", confidence: float = 1.0):
    """
    Update the importance score for a node
    """
    try:
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            logger.error(f"Node {node_id} not found")
            return
        
        # Update or create attributes
        if not node.attributes:
            node.attributes = {}
        
        node.attributes['importance'] = importance
        node.attributes['importance_reasoning'] = reasoning
        node.attributes['importance_confidence'] = confidence
        node.attributes['importance_calculated_at'] = str(datetime.now())
        
        session.commit()
        logger.info(f"Updated importance for {node.label}: {importance}")
        
    except Exception as e:
        logger.error(f"Error updating importance for node {node_id}: {e}")
        session.rollback()


def get_importance_stats():
    """
    Get statistics about node importance distribution
    """
    session = get_session()
    
    # Get all nodes with importance scores
    nodes_with_importance = session.query(Node).filter(
        Node.attributes.has_key('importance')
    ).all()
    
    importance_ranges = {
        "critical": 0,      # >= 0.9
        "high": 0,          # 0.7 - 0.89
        "medium": 0,        # 0.4 - 0.69
        "low": 0,           # 0.1 - 0.39
        "minimal": 0        # < 0.1
    }
    
    for node in nodes_with_importance:
        importance = node.attributes.get('importance', 0.0)
        
        if importance >= 0.9:
            importance_ranges["critical"] += 1
        elif importance >= 0.7:
            importance_ranges["high"] += 1
        elif importance >= 0.4:
            importance_ranges["medium"] += 1
        elif importance >= 0.1:
            importance_ranges["low"] += 1
        else:
            importance_ranges["minimal"] += 1
    
    return {
        "total_nodes_with_importance": len(nodes_with_importance),
        "importance_distribution": importance_ranges
    }


if __name__ == "__main__":
    from datetime import datetime
    
    # Show stats first
    stats = get_importance_stats()
    
    print(f"Importance Stats:")
    print(f"  Total nodes with importance: {stats['total_nodes_with_importance']}")
    print(f"  Critical importance (>=0.9): {stats['importance_distribution']['critical']}")
    print(f"  High importance (0.7-0.89): {stats['importance_distribution']['high']}")
    print(f"  Medium importance (0.4-0.69): {stats['importance_distribution']['medium']}")
    print(f"  Low importance (0.1-0.39): {stats['importance_distribution']['low']}")
    print(f"  Minimal importance (<0.1): {stats['importance_distribution']['minimal']}")
    print()
    
    # Run importance pipeline
    print("Running importance calculation pipeline...")
    result = run_importance_pipeline()
    print(f"Result: {result}")
