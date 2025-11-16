"""
Simple Entity Card Pipeline
Creates entity cards for each node in the knowledge graph using existing tools
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_core.kg_tools import inspect_node_neighborhood
from app.assistant.entity_management.entity_cards import (
    create_entity_card, 
    get_entity_card_by_name, 
    get_entity_card_stats,
    initialize_entity_cards_db
)
from app.models.maintenance_logs import (
    get_last_maintenance_run_time,
    log_maintenance_run,
    get_nodes_updated_since
)
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

BATCH_SIZE = 20  # Process edges in batches like description creator


def run_entity_card_pipeline(min_outgoing_edges: int = 0, incremental: bool = False):
    """
    Main pipeline function to create entity cards for nodes with optional filtering
    
    Args:
        min_outgoing_edges: Minimum number of outgoing edges required (default: 0 = include all nodes including leafs)
    """
    session = get_session()
    entity_card_agent = DI.agent_factory.create_agent("entity_card_generator")
    
    # Track run start time for performance monitoring
    run_start_time = datetime.now(timezone.utc)
    
    # Get nodes based on filtering criteria and incremental processing
    if incremental:
        # Get last run time
        last_run_time = get_last_maintenance_run_time(session, "entity_card_generation")
        last_run_time = datetime.now(timezone.utc) - timedelta(weeks=5)
        if last_run_time:
            # Get only nodes updated since last run
            nodes_with_edges = get_nodes_updated_since(session, last_run_time)
            logger.info(f"Incremental processing: Found {len(nodes_with_edges)} nodes updated since {last_run_time}")
        else:
            # First run - process all nodes
            nodes_with_edges = get_nodes_with_edges(session, min_outgoing_edges)
            logger.info(f"First incremental run: Processing {len(nodes_with_edges)} nodes")
    else:


        # Use only edge count filtering (now includes leaf nodes by default)
        nodes_with_edges = get_nodes_with_edges(session, min_outgoing_edges)
        logger.info(f"Full processing: {len(nodes_with_edges)} nodes with {min_outgoing_edges}+ outgoing edges for entity cards (including leaf nodes)")
    
    processed_count = 0
    error_count = 0
    skipped_count = 0
    agent_rejected_count = 0
    
    for node in nodes_with_edges:
        # Skip nodes with label "Jukka" (hardcoded for now)
        if node.label == "Jukka":
            logger.info(f"Skipping node: {node.label} (hardcoded skip)")
            skipped_count += 1
            continue
            
        logger.info(f"Processing node: {node.label} ({node.id})")
        
        try:
            # Get node neighborhood data using existing tool
            node_info, all_edges = inspect_node_neighborhood(node.id, session)
            
            logger.info(f" - Processing {len(all_edges)} relationships for {node.label}")
            
            # Format relationships as a string for blackboard injection
            relationships_text = []
            for i, rel in enumerate(all_edges, 1):
                rel_text = f"{i}. {rel['direction'].title()} relationship: {rel['edge_type']}\n"
                rel_text += f"   - Connected to: {rel['connected_node']['label']} ({rel['connected_node']['type']})"
                
                # For contact information, show the actual value clearly
                if rel['edge_type'] in ['has_phone', 'has_email']:
                    rel_text += f"\n   - Value: {rel['connected_node']['label']}"
                
                if rel['connected_node'].get('description'):
                    desc = rel['connected_node']['description'][:100]
                    if len(rel['connected_node']['description']) > 100:
                        desc += "..."
                    rel_text += f"\n   - Description: {desc}"
                relationships_text.append(rel_text)
            
            relationships_data = f"Total relationships: {len(all_edges)}\n" + "\n".join(relationships_text)
            
            # Prepare data for the agent with string values for blackboard injection
            agent_input = {
                "entity_name": node_info.get('label', ''),
                "entity_type": node_info.get('type', ''),
                "entity_description": node_info.get('description', ''),
                "entity_aliases": ", ".join(node_info.get('aliases', [])),
                "relationships_data": relationships_data
            }
            
            # Call the agent to decide whether to create a card
            response = entity_card_agent.action_handler(Message(agent_input=agent_input))
            
            if response and response.data:
                entity_card = response.data
                
                # Check if the agent decided to create a card
                if entity_card.get('should_create_card', False):
                    logger.info(f" - Agent approved: Generated entity card for {node.label}")
                    # Store the entity card in database
                    store_entity_card_in_db(session, node.label, entity_card, node.id, node_info)
                    processed_count += 1
                else:
                    logger.info(f" - Agent rejected: Skipping {node.label} (not useful for prompt injection)")
                    agent_rejected_count += 1
            else:
                error_count += 1
                logger.error(f" - Failed to generate entity card for {node.label}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing node {node.label}: {e}")
            session.rollback()
    
    # Calculate run duration
    run_duration = (datetime.now(timezone.utc) - run_start_time).total_seconds()
    
    # Log the run
    current_time = datetime.now(timezone.utc)
    log_maintenance_run(
        session=session,
        task_name="entity_card_generation",
        last_run_time=current_time,
        nodes_processed=len(nodes_with_edges),
        nodes_updated=processed_count,
        run_duration_seconds=run_duration
    )
    
    logger.info(f"Pipeline completed: {processed_count} processed, {error_count} errors, {skipped_count} skipped, {agent_rejected_count} agent rejected")
    logger.info(f"Run duration: {run_duration:.2f} seconds")
    
    return {
        "processed": processed_count, 
        "errors": error_count, 
        "skipped": skipped_count,
        "agent_rejected": agent_rejected_count,
        "run_duration_seconds": run_duration,
        "incremental": incremental
    }


def get_nodes_with_edges(session: Session, min_outgoing_edges: int = 0) -> List[Node]:
    """
    Get nodes that have at least the specified number of outgoing edges
    If min_outgoing_edges = 0, include all nodes (including leaf nodes)
    """
    if min_outgoing_edges == 0:
        # Include all nodes (including leaf nodes with no outgoing edges)
        return session.query(Node).all()
    elif min_outgoing_edges == 1:
        # Simple case: just get nodes with any outgoing edges
        return session.query(Node).join(Edge, Node.id == Edge.source_id).distinct().all()
    else:
        # More complex case: count outgoing edges and filter
        from sqlalchemy import func
        nodes_with_counts = session.query(
            Node, 
            func.count(Edge.id).label('outgoing_count')
        ).join(Edge, Node.id == Edge.source_id).group_by(Node.id).having(
            func.count(Edge.id) >= min_outgoing_edges
        ).all()
        
        return [node for node, count in nodes_with_counts]





def chunk_edges(edges: List[Dict[str, Any]], batch_size: int) -> List[List[Dict[str, Any]]]:
    """
    Split edges into chunks for batch processing
    """
    return [edges[i:i + batch_size] for i in range(0, len(edges), batch_size)]


def store_entity_card_in_db(session, entity_name: str, entity_card: Dict[str, Any], source_node_id=None, node_info=None):
    try:
        existing_card = get_entity_card_by_name(session, entity_name)

        # Extract original KG data
        original_description = node_info.get('description') if node_info else None
        original_aliases = node_info.get('aliases', []) if node_info else []

        # Build metadata JSON
        import json
        meta = json.dumps(entity_card.get('card_metadata', []))

        if existing_card:
            logger.info(f"Entity card for {entity_name} exists, overwriting")
            existing_card.entity_type = entity_card.get('entity_type', 'unknown')
            existing_card.summary = entity_card.get('summary', '')
            existing_card.source_node_id = source_node_id
            existing_card.original_description = original_description
            existing_card.original_aliases = original_aliases
            existing_card.key_facts = entity_card.get('key_facts', [])
            existing_card.relationships = entity_card.get('relationships', [])
            existing_card.aliases = entity_card.get('aliases', [])
            existing_card.confidence = entity_card.get('confidence')
            existing_card.batch_number = entity_card.get('batch_number')
            existing_card.total_batches = entity_card.get('total_batches')
            existing_card.card_metadata = meta
        else:
            logger.info(f"Creating new entity card for {entity_name}")
            existing_card = create_entity_card(
                session=session,
                entity_name=entity_name,
                entity_type=entity_card.get('entity_type', 'unknown'),
                summary=entity_card.get('summary', ''),
                source_node_id=source_node_id,
                original_description=original_description,
                original_aliases=original_aliases,
                key_facts=entity_card.get('key_facts', []),
                relationships=entity_card.get('relationships', []),
                aliases=entity_card.get('aliases', []),
                confidence=entity_card.get('confidence'),
                batch_number=entity_card.get('batch_number'),
                total_batches=entity_card.get('total_batches'),
                card_metadata=meta,
            )

        session.commit()
        return existing_card

    except Exception as e:
        logger.error(f"Error storing entity card for {entity_name}: {e}")
        session.rollback()
        return None



def store_entity_card(entity_name: str, entity_card: Dict[str, Any]):
    """
    Legacy function - now uses database storage
    """
    session = get_session()
    return store_entity_card_in_db(session, entity_name, entity_card)


def process_single_node(node_name: str):
    """
    Process a single node by name
    """
    session = get_session()
    entity_card_agent = DI.agent_factory.create_agent("entity_card_generator")
    
    # Find the node
    node = session.query(Node).filter(Node.label == node_name).first()
    if not node:
        logger.error(f"Node '{node_name}' not found")
        return None
    
    try:
        # Get node neighborhood data
        node_info, all_edges = inspect_node_neighborhood(node.id, session)
        
        # Format relationships as a string for blackboard injection
        relationships_text = []
        for i, rel in enumerate(all_edges, 1):
            rel_text = f"{i}. {rel['direction'].title()} relationship: {rel['edge_type']}\n"
            rel_text += f"   - Connected to: {rel['connected_node']['label']} ({rel['connected_node']['type']})"
            
            # For contact information, show the actual value clearly
            if rel['edge_type'] in ['has_phone', 'has_email']:
                rel_text += f"\n   - Value: {rel['connected_node']['label']}"
            
            if rel['connected_node'].get('description'):
                desc = rel['connected_node']['description'][:100]
                if len(rel['connected_node']['description']) > 100:
                    desc += "..."
                rel_text += f"\n   - Description: {desc}"
            relationships_text.append(rel_text)
        
        relationships_data = f"Total relationships: {len(all_edges)}\n" + "\n".join(relationships_text)
        
        # Prepare data for the agent with string values for blackboard injection
        agent_input = {
            "entity_name": node_info.get('label', ''),
            "entity_type": node_info.get('type', ''),
            "entity_description": node_info.get('description', ''),
            "entity_aliases": ", ".join(node_info.get('aliases', [])),
            "relationships_data": relationships_data
        }
        
        # Call the agent to decide whether to create a card
        response = entity_card_agent.action_handler(Message(agent_input=agent_input))
        
        if response and response.data:
            entity_card = response.data
            
            # Check if the agent decided to create a card
            if entity_card.get('should_create_card', False):
                logger.info(f"Agent approved: Generated entity card for {node_name}")
                # Store in database
                db_card = store_entity_card_in_db(session, node_name, entity_card, node.id, node_info)
                return entity_card if db_card else None
            else:
                logger.info(f"Agent rejected: Skipping {node_name} (not useful for prompt injection)")
                return {"decision": "rejected", "reason": "Agent determined not useful for prompt injection"}
        else:
            logger.error(f"No entity card generated for {node_name}")
            return None
            
    except Exception as e:
        logger.error(f"Error processing node {node_name}: {e}")
        return None


def get_pipeline_stats():
    """
    Get statistics about nodes and their edge counts
    """
    session = get_session()
    
    # Get total nodes
    total_nodes = session.query(Node).count()
    
    # Get nodes with outgoing edges
    nodes_with_outgoing = session.query(Node).join(Edge, Node.id == Edge.source_id).distinct().count()
    
    # Get nodes with multiple outgoing edges
    from sqlalchemy import func
    nodes_with_multiple = session.query(func.count(Node.id)).join(
        Edge, Node.id == Edge.source_id
    ).group_by(Node.id).having(func.count(Edge.id) >= 2).count()
    
    return {
        "total_nodes": total_nodes,
        "nodes_with_outgoing_edges": nodes_with_outgoing,
        "nodes_with_multiple_outgoing": nodes_with_multiple,
        "isolated_nodes": total_nodes - nodes_with_outgoing
    }


def get_entity_card_database_stats():
    """
    Get statistics about entity cards in the database
    """
    session = get_session()
    return get_entity_card_stats(session)


def run_incremental_entity_card_pipeline():
    """
    Run entity card pipeline only for nodes that have been updated since the last run
    """
    return run_entity_card_pipeline(incremental=True)


def get_entity_card_run_history(session=None, limit=10):
    """
    Get recent entity card generation run history
    """
    own_session = False
    if session is None:
        session = get_session()
        own_session = True
    
    try:
        from app.assistant.entity_management.entity_cards import EntityCardRunLog
        runs = session.query(EntityCardRunLog).order_by(
            EntityCardRunLog.created_at.desc()
        ).limit(limit).all()
        
        return [
            {
                'id': run.id,
                'last_run_time': run.last_run_time,
                'nodes_processed': run.nodes_processed,
                'nodes_updated': run.nodes_updated,
                'run_duration_seconds': run.run_duration_seconds,
                'created_at': run.created_at
            }
            for run in runs
        ]
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    # Initialize entity cards database
    initialize_entity_cards_db()
    
    # Show stats first
    stats = get_pipeline_stats()
    entity_card_stats = get_entity_card_database_stats()
    
    print(f"Pipeline Stats:")
    print(f"  Total nodes: {stats['total_nodes']}")
    print(f"  Nodes with outgoing edges: {stats['nodes_with_outgoing_edges']}")
    print(f"  Nodes with multiple outgoing: {stats['nodes_with_multiple_outgoing']}")
    print(f"  Isolated nodes: {stats['isolated_nodes']}")
    print()
    print(f"Entity Card Database Stats:")
    print(f"  Total cards: {entity_card_stats['total_cards']}")
    print(f"  Active cards: {entity_card_stats['active_cards']}")
    print(f"  Total usage: {entity_card_stats['total_usage']}")
    print()
    
    # Show run history
    print("Recent entity card generation runs:")
    run_history = get_entity_card_run_history(limit=5)
    for run in run_history:
        print(f"  {run['created_at']}: {run['nodes_processed']} processed, {run['nodes_updated']} updated, {run['run_duration_seconds']:.2f}s")
    print()
    
    # Run pipeline with agent decision-making (include all nodes)
    print("Running incremental entity card pipeline...")
    result = run_incremental_entity_card_pipeline()
    print(f"Result: {result}")
