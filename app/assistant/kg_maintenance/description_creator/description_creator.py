# kg_maintenance/description_creator.py
import json
from datetime import datetime, timezone
from sqlalchemy import func
from collections import defaultdict, deque
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_core.kg_tools import inspect_node_neighborhood
from app.models.maintenance_logs import get_last_maintenance_run_time, log_maintenance_run, get_nodes_updated_since
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI

BATCH_SIZE = 20

def order_nodes_by_jukka_distance_and_connections(nodes, session):
    """
    Order nodes by their distance from 'Jukka' and connection count.
    
    Priority order:
    1. Nodes 0 hops from Jukka (Jukka itself), ordered by connection count (desc)
    2. Nodes 1 hop from Jukka, ordered by connection count (desc)
    3. Nodes 2 hops from Jukka, ordered by connection count (desc)
    4. etc.
    
    Args:
        nodes: List of Node objects to order
        session: Database session
        
    Returns:
        List of Node objects ordered by priority
    """
    if not nodes:
        return []
    
    # Find Jukka node
    jukka_node = session.query(Node).filter(Node.label.ilike('%jukka%')).first()
    if not jukka_node:
        print("⚠️ Warning: No 'Jukka' node found. Ordering by connection count only.")
        return order_nodes_by_connection_count(nodes, session)
    
    print(f"🎯 Found Jukka node: {jukka_node.label} ({jukka_node.id})")
    
    # Build adjacency list for BFS
    node_ids = {node.id for node in nodes}
    adjacency = defaultdict(set)
    
    # Get all edges between our nodes
    edges = session.query(Edge).filter(
        Edge.source_id.in_(node_ids),
        Edge.target_id.in_(node_ids)
    ).all()
    
    for edge in edges:
        adjacency[edge.source_id].add(edge.target_id)
        adjacency[edge.target_id].add(edge.source_id)
    
    # BFS to find distances from Jukka
    distances = {}
    queue = deque([(jukka_node.id, 0)])
    visited = {jukka_node.id}
    
    while queue:
        node_id, distance = queue.popleft()
        distances[node_id] = distance
        
        for neighbor in adjacency[node_id]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    
    # Calculate connection counts for each node
    connection_counts = {}
    for node in nodes:
        count = len(adjacency.get(node.id, set()))
        connection_counts[node.id] = count
    
    # Group nodes by distance from Jukka
    distance_groups = defaultdict(list)
    for node in nodes:
        distance = distances.get(node.id, float('inf'))  # inf for unreachable nodes
        distance_groups[distance].append(node)
    
    # Sort each distance group by connection count (descending)
    ordered_nodes = []
    for distance in sorted(distance_groups.keys()):
        if distance == float('inf'):
            # Unreachable nodes go last
            group_nodes = distance_groups[distance]
            group_nodes.sort(key=lambda n: connection_counts[n.id], reverse=True)
            ordered_nodes.extend(group_nodes)
        else:
            # Reachable nodes, sorted by connection count
            group_nodes = distance_groups[distance]
            group_nodes.sort(key=lambda n: connection_counts[n.id], reverse=True)
            ordered_nodes.extend(group_nodes)
    
    # Print summary
    print(f"📊 Node ordering summary:")
    for distance in sorted(distance_groups.keys()):
        if distance == float('inf'):
            print(f"  - Unreachable from Jukka: {len(distance_groups[distance])} nodes")
        else:
            print(f"  - {distance} hops from Jukka: {len(distance_groups[distance])} nodes")
    
    return ordered_nodes

def order_nodes_by_connection_count(nodes, session):
    """
    Fallback: Order nodes by connection count only.
    
    Args:
        nodes: List of Node objects to order
        session: Database session
        
    Returns:
        List of Node objects ordered by connection count (descending)
    """
    node_ids = {node.id for node in nodes}
    
    # Count connections for each node
    connection_counts = {}
    for node in nodes:
        count = session.query(Edge).filter(
            (Edge.source_id == node.id) | (Edge.target_id == node.id)
        ).count()
        connection_counts[node.id] = count
    
    # Sort by connection count (descending)
    return sorted(nodes, key=lambda n: connection_counts[n.id], reverse=True)

def run_description_pass(incremental: bool = True, today_only: bool = False):
    """
    Run description creation pass for nodes in the knowledge graph.
    
    Args:
        incremental (bool): If True, only process nodes updated since last run.
                          If False, process all nodes (full run).
        today_only (bool): If True, only process nodes created today (temporary fix).
    """
    session = get_session()
    description_agent = DI.agent_factory.create_agent("kg_maintenance::description_creator")
    
    run_start_time = datetime.now(timezone.utc)
    
    # Initialize maintenance logs table if it doesn't exist
    try:
        from app.models.maintenance_logs import initialize_maintenance_logs_db
        initialize_maintenance_logs_db()
        print("✅ Maintenance logs table initialized")
    except Exception as e:
        if "already exists" not in str(e):
            print(f"⚠️ Warning: Could not initialize maintenance logs: {e}")
    
    # Check if this is the first run ever
    try:
        last_run_time = get_last_maintenance_run_time(session, "description_creation")
        is_first_run = last_run_time is None
    except Exception as e:
        print(f"⚠️ Warning: Could not check last run time: {e}")
        last_run_time = None
        is_first_run = True
    
    if today_only:
        # Temporary fix: only process nodes created today
        from datetime import date
        today = date.today()
        nodes_to_process = session.query(Node).filter(
            func.date(Node.created_at) == today
        ).filter(
            Node.node_type.in_(['Entity', 'State', 'Event', 'Goal', 'Property'])
        ).all()
        print(f"Today-only processing: Found {len(nodes_to_process)} nodes created today ({today})")
        actual_mode = "today_only"
    elif incremental:
        if is_first_run:
            # First run ever - process all nodes but mark as first run
            nodes_to_process = session.query(Node).filter(
                Node.node_type.in_(['Entity', 'State', 'Event', 'Goal', 'Property'])
            ).all()
            print(f"First run ever: Processing {len(nodes_to_process)} nodes (all nodes)")
            actual_mode = "first_run"
        else:
            # Incremental run - only process updated nodes
            all_updated_nodes = get_nodes_updated_since(session, last_run_time)
            nodes_to_process = [node for node in all_updated_nodes if node.node_type in ['Entity', 'State', 'Event', 'Goal', 'Property']]
            print(f"Incremental processing: Found {len(nodes_to_process)} nodes updated since {last_run_time}")
            actual_mode = "incremental"
    else:
        # Full run - process all nodes
        nodes_to_process = session.query(Node).filter(
            Node.node_type.in_(['Entity', 'State', 'Event', 'Goal', 'Property'])
        ).all()
        print(f"Full run: Processing {len(nodes_to_process)} nodes")
        actual_mode = "full"
    
    # Order nodes by distance from Jukka and connection count
    print(f"\n🔄 Ordering {len(nodes_to_process)} nodes by distance from Jukka and connection count...")
    print(f"📋 Processing node types: Entity, State, Event, Goal, Property (excluding Concept nodes)")
    ordered_nodes = order_nodes_by_jukka_distance_and_connections(nodes_to_process, session)
    
    processed_count = 0
    updated_count = 0
    error_count = 0
    current_distance = None
    
    for i, node in enumerate(ordered_nodes):
        # Show progress and distance group info
        if i == 0 or (i % 10 == 0):
            print(f"\n📈 Progress: {i}/{len(ordered_nodes)} nodes processed")
        
        # Skip nodes that already have descriptions
        if node.description and len(node.description.strip()) > 0:
            print(f" - Skipping {node.label} (already has description)")
            continue
            
        print(f"\nProcessing node: {node.label} ({node.id})")
        processed_count += 1

        try:
            node_info, all_edges = inspect_node_neighborhood(node.id, session)
            chunks = chunk_edges(all_edges, BATCH_SIZE)

            description = ""  # Start clean. Only use after first batch.

            for i, chunk in enumerate(chunks):
                print(f" - Processing batch {i + 1} of {len(chunks)}")

                partial_neighborhood = {
                    "node": node_info,
                    "edges": chunk
                }

                agent_input = {
                    "node_label": node_info["label"],
                    "node_type": node_info["type"],
                    "node_aliases": node_info["aliases"],
                    "node_attributes": node_info["attributes"],
                    "neighborhood_data": json.dumps(partial_neighborhood),
                    "prior_description": description if len(all_edges) > BATCH_SIZE else ""
                }

                if i > 0 and description:
                    agent_input["prior_description"] = description

                response = description_agent.action_handler(Message(agent_input=agent_input)).data or {}
                new_description = response.get("new_description")
                if new_description:
                    description = new_description
                else:
                    print("   ⚠️ No updated description returned, keeping previous.")

            if description and description != node.description:
                print(f" - Saving updated description. {description}")
                node.description = description
                session.commit()
                updated_count += 1
            else:
                print(" - No change to description.")

        except Exception as e:
            print(f"   ❌ Error while processing node {node.label}: {e}")
            session.rollback()
            error_count += 1
    
    # Log the run
    run_duration = (datetime.now(timezone.utc) - run_start_time).total_seconds()
    current_time = datetime.now(timezone.utc)
    try:
        log_maintenance_run(
            session=session,
            task_name="description_creation",
            last_run_time=current_time,
            nodes_processed=processed_count,
            nodes_updated=updated_count,
            run_duration_seconds=run_duration
        )
        print("✅ Run logged successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not log run: {e}")
    
    print(f"\nDescription creation completed:")
    print(f"  - Nodes processed: {processed_count}")
    print(f"  - Nodes updated: {updated_count}")
    print(f"  - Errors: {error_count}")
    print(f"  - Run duration: {run_duration:.2f} seconds")
    print(f"  - Mode: {actual_mode}")
    
    return {
        "processed": processed_count,
        "updated": updated_count,
        "errors": error_count,
        "run_duration_seconds": run_duration,
        "mode": actual_mode,
        "incremental": incremental  # Keep for backward compatibility
    }

def run_incremental_description_pass():
    """
    Convenience function for incremental description creation
    """
    return run_description_pass(incremental=True)

def run_full_description_pass():
    """
    Convenience function for full description creation
    """
    return run_description_pass(incremental=False)

def run_today_only_description_pass():
    """
    Convenience function for today-only description creation (temporary fix)
    """
    return run_description_pass(today_only=True)

def get_description_run_history(session=None, limit=10):
    """
    Get recent description creation run history
    """
    from app.models.maintenance_logs import get_maintenance_run_history
    return get_maintenance_run_history(session=session, task_name="description_creation", limit=limit)

def chunk_edges(edges, batch_size):
    return [edges[i:i + batch_size] for i in range(0, len(edges), batch_size)]

if __name__ == "__main__":
    import app.assistant.tests.test_setup
    # Example usage
    print("Running incremental description creation...")
    result = run_incremental_description_pass()
    print(f"Result: {result}")
    
    print("\nRecent run history:")
    history = get_description_run_history()
    for run in history:
        print(f"  {run['last_run_time']}: {run['nodes_processed']} processed, {run['nodes_updated']} updated")
