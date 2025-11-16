# kg_maintenance_manager.py
import json

from app.models.base import get_session
from app.assistant.kg_core.kg_tools import get_nodes_by_connection_count, get_similar_edges_for_node, safe_add_relationship_by_id, \
    delete_edge
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.kg_core.knowledge_graph_db import Edge

BATCH_SIZE = 50


def run_kg_maintenance():
    session = get_session()
    print("Fetching nodes by connection count...")
    nodes = get_nodes_by_connection_count(session)

    for node in nodes:
        print(f"\nProcessing node {node.label} ({node.id})")

        # get_similar_edges_for_node already groups edges by (source_id, target_id, relationship_type)
        # implicitly, as it processes outgoing edges from a single node_id and groups by (target_id, relationship_type).
        edge_groups = get_similar_edges_for_node(node.id, session)

        for group in edge_groups:
            if not group or len(group) < 2:
                continue

            # This comment is now accurate: all edges in 'group' share the same source, target, and type.
            print(f"Found {len(group)} similar edges between same nodes and same type.")

            # Extract common source and target IDs for this group once.
            # This is safe because get_similar_edges_for_node guarantees this grouping.
            common_source_id = group[0].source_id
            common_target_id = group[0].target_id
            print(f" - Common Source Node ID: {common_source_id}")
            print(f" - Common Target Node ID: {common_target_id}")

            for i in range(0, len(group), BATCH_SIZE):
                batch = group[i:i + BATCH_SIZE]
                # Pass the common source and target IDs explicitly to process_edge_batch
                process_edge_batch(batch, session, common_source_id, common_target_id)

    print("Maintenance complete.")


def process_edge_batch(edge_batch, session, common_source_id, common_target_id):
    """
    Sends a batch of similar edges to the edge_merger agent and prints merge decisions.
    """
    if not edge_batch:
        return
    edge_merger_agent = DI.agent_factory.create_agent("kg_maintenance::edge_merger")
    edge_merger_data = DI.agent_factory.create_agent("kg_maintenance::edge_merger_data")
    # Prepare context for the agent
    parsed_edges = []
    for edge in edge_batch:
        parsed_edges.append({
            "edge_id": str(edge.id),
            "relationship_type": edge.relationship_type,
            "attributes": edge.attributes or {},
        })

    merge_candidates = json.dumps(parsed_edges)
    context_input = {"merge_candidates": merge_candidates}
    response = edge_merger_agent.action_handler(Message(agent_input=context_input)).data or {}

    edge_ids = response.get("edges_for_merging", [])
    human_review = response.get("human_review", False)
    if human_review:
        print(f"Human Review needed for edges: {response}")
        return
    if not edge_ids:
        print(" - No merges suggested.")
        return

    if 0 < len(edge_ids) < 2:
        print(
            f"⚠️ Safeguard Triggered: Agent suggested an invalid merge with only {len(edge_ids)} edge(s). Aborting this batch.")
        return

    edges = session.query(Edge).filter(Edge.id.in_(edge_ids)).all()

    merge_edge_data = []
    for edge in edges:
        merge_edge_data.append({
            "edge_id": str(edge.id),
            "relationship_type": edge.relationship_type,
            "attributes": edge.attributes or {},
        })

    merge_edge_data_input = {"merge_edge_data_input": json.dumps(merge_edge_data)}

    merged_data = edge_merger_data.action_handler(Message(agent_input=merge_edge_data_input)).data or {}

    print(merged_data)

    try:

        # Use the common_source_id and common_target_id passed explicitly
        source_id_for_new_edge = common_source_id
        target_id_for_new_edge = common_target_id

        # Prepare attributes for the new merged edge (updated for current schema)
        new_edge_attributes = {
            "importance": merged_data.get('importance', 0.0),
            "credibility": merged_data.get('credibility', 0.0),
            "valid_during": merged_data.get('valid_during', ""),
            # Note: start_time/end_time removed - use start_date/end_date on nodes instead
            # context_window removed - use sentence field on edges instead
        }

        merged_relationship_type = merged_data.get('merged_relationship_type')
        if not merged_relationship_type:
            print(" - Merge aborted: No relationship_type returned from agent.")
            session.rollback()
            return

        # Create the new merged edge
        new_edge, status = safe_add_relationship_by_id(
            db_session=session,
            source_id=source_id_for_new_edge,
            target_id=target_id_for_new_edge,
            relationship_type=merged_relationship_type,
            attributes=new_edge_attributes
        )

        # Only proceed if the new edge was successfully created
        if status == "created":
            session.flush()
            print(f" - Created new merged edge (ID: {new_edge.id}, Type: {new_edge.relationship_type})")

            # Delete the original edges
            for edge in edges:
                delete_edge(edge.id, session)
            print(f" - Deleted {len(edges)} redundant edges.")

            session.commit()
            print(" - Merge and deletion committed successfully.")
        elif status == "found":
            session.rollback()  # Rollback because no changes should be made
            print(f" - Merge aborted: An identical edge already exists (ID: {new_edge.id}).")
        else:  # Handles "error_missing_nodes" or other errors
            session.rollback()
            print(f" - Merge aborted: Could not create new edge (Status: {status}).")


    except Exception as e:
        session.rollback()
        print(f" - Error processing merged data or performing database operations: {e}")
        print(" - Transaction rolled back.")


if __name__ == "__main__":
    run_kg_maintenance()
