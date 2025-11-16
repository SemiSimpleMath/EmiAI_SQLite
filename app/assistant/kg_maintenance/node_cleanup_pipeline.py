"""
Node Cleanup Pipeline
Identifies suspect nodes that should potentially be deleted
"""

import json
import time
from typing import List, Dict, Tuple
from collections import defaultdict, deque
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_core.kg_tools import inspect_node_neighborhood
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

# Import the new tracking system
from app.models.node_analysis_tracking import (
    initialize_node_analysis_tracking_db,
    get_node_analysis_status,
    mark_node_as_analyzed,
    get_nodes_needing_analysis,
    get_analysis_statistics
)

logger = get_logger(__name__)


def find_jukka_node(session: Session) -> Node:
    """Find the Jukka node in the database (case insensitive)"""
    # Try exact match first
    jukka_node = session.query(Node).filter(Node.label == "Jukka").first()
    if jukka_node:
        return jukka_node
    
    # Try case-insensitive search
    jukka_node = session.query(Node).filter(Node.label.ilike("Jukka")).first()
    if jukka_node:
        return jukka_node
    
    # Try other common variations
    jukka_node = session.query(Node).filter(Node.label.ilike("jukka")).first()
    if jukka_node:
        return jukka_node
    
    # List all nodes to help debug
    all_nodes = session.query(Node).all()
    print(f"Available nodes in database ({len(all_nodes)} total):")
    for node in all_nodes[:20]:  # Show first 20
        print(f"  - '{node.label}' (type: '{node.node_type}')")
    if len(all_nodes) > 20:
        print(f"  ... and {len(all_nodes) - 20} more")
    
    raise ValueError("Jukka node not found in database")


def calculate_distances_from_jukka(session: Session) -> Dict[str, int]:
    """
    Calculate the shortest distance from Jukka to all other nodes using BFS
    Returns a dictionary mapping node_id -> distance
    """
    jukka_node = find_jukka_node(session)
    
    # Get all nodes and edges
    all_nodes = session.query(Node).all()
    all_edges = session.query(Edge).all()
    
    # Build adjacency list
    adjacency = defaultdict(list)
    for edge in all_edges:
        adjacency[str(edge.source_id)].append(str(edge.target_id))
        adjacency[str(edge.target_id)].append(str(edge.source_id))  # Undirected graph
    
    # BFS to calculate distances
    distances = {}
    queue = deque([(str(jukka_node.id), 0)])
    visited = set()
    
    while queue:
        node_id, distance = queue.popleft()
        if node_id in visited:
            continue
            
        visited.add(node_id)
        distances[node_id] = distance
        
        # Add neighbors to queue
        for neighbor_id in adjacency[node_id]:
            if neighbor_id not in visited:
                queue.append((neighbor_id, distance + 1))
    
    return distances


def get_connection_to_jukka(node_id: str, distances: Dict[str, int], session: Session) -> Tuple[str, int]:
    """
    Get information about how a node connects to Jukka
    Returns (connection_description, distance)
    """
    distance = distances.get(node_id, -1)
    
    if distance == 0:
        return "This IS Jukka", 0
    elif distance == 1:
        return "Direct connection to Jukka", 1
    elif distance == 2:
        return "Connected to Jukka via 1 intermediate node", 2
    elif distance == 3:
        return "Connected to Jukka via 2 intermediate nodes", 3
    elif distance > 3:
        return f"Connected to Jukka via {distance-1} intermediate nodes", distance
    else:
        return "Not connected to Jukka", -1


def run_node_cleanup_pipeline(skip_analyzed: bool = True, force_reanalyze: bool = False, max_nodes: int = None):
    """
    Main pipeline function to identify suspect nodes
    
    Args:
        skip_analyzed: If True, skip nodes that have already been analyzed
        force_reanalyze: If True, reanalyze all nodes regardless of previous analysis
        max_nodes: Maximum number of nodes to process (None for all)
    """
    session = get_session()
    
    try:
        # Initialize the tracking database if it doesn't exist
        initialize_node_analysis_tracking_db()
        
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        logger.info(f"🔍 Connecting to database: {db_uri}")
        
        # Get analysis statistics
        stats = get_analysis_statistics(session)
        logger.info(f"📊 Current analysis coverage: {stats['analyzed_nodes']}/{stats['total_nodes']} nodes ({stats['coverage_percentage']:.1f}%)")
        
        cleanup_agent = DI.agent_factory.create_agent("kg_maintenance::node_cleanup")
        
        # Calculate distances from Jukka
        logger.info("Calculating distances from Jukka...")
        distances = calculate_distances_from_jukka(session)
        logger.info(f"Calculated distances for {len(distances)} nodes")
        
        # Determine which nodes to process
        if force_reanalyze:
            # Process all nodes
            nodes_to_process = session.query(Node).all()
            logger.info(f"🔄 Force reanalyze mode: Processing all {len(nodes_to_process)} nodes")
        elif skip_analyzed:
            # Only process unanalyzed nodes
            unanalyzed_node_ids = get_nodes_needing_analysis(session, limit=max_nodes)
            if unanalyzed_node_ids:
                nodes_to_process = session.query(Node).filter(Node.id.in_(unanalyzed_node_ids)).all()
                logger.info(f"⏭️ Skip analyzed mode: Processing {len(nodes_to_process)} unanalyzed nodes")
            else:
                logger.info("✅ All nodes have been analyzed! No work to do.")
                return {
                    "processed": 0,
                    "suspect_count": 0,
                    "errors": 0,
                    "suspect_nodes": [],
                    "coverage": stats
                }
        else:
            # Process all nodes (legacy behavior)
            nodes_to_process = session.query(Node).all()
            logger.info(f"📝 Legacy mode: Processing all {len(nodes_to_process)} nodes")
        
        suspect_nodes = []
        processed_count = 0
        error_count = 0
        skipped_count = 0
        
        for node in nodes_to_process:
            # Skip Jukka himself
            if node.label == "Jukka":
                continue
            
            # Check if node was already analyzed (unless force reanalyze)
            if not force_reanalyze and skip_analyzed:
                analysis_status = get_node_analysis_status(session, str(node.id))
                if analysis_status:
                    # Node was already analyzed, skip it
                    skipped_count += 1
                    if skipped_count % 100 == 0:  # Log every 100 skipped nodes
                        logger.info(f"⏭️ Skipped {skipped_count} already analyzed nodes...")
                    continue
            
            logger.info(f"Processing node: {node.label} ({node.id})")
            
            # Start timing the analysis
            analysis_start_time = time.time()
            
            try:
                # Get node neighborhood data
                node_info, all_edges = inspect_node_neighborhood(node.id, session)
                edge_count = len(all_edges)
                
                # Get connection info to Jukka
                connection_desc, jukka_distance = get_connection_to_jukka(
                    str(node.id), distances, session
                )
                
                logger.info(f" - {edge_count} edges, {jukka_distance} hops from Jukka")
                
                # Format neighborhood data as string
                neighborhood_text = []
                for i, rel in enumerate(all_edges, 1):
                    rel_text = f"{i}. {rel['direction'].title()} relationship: {rel['edge_type']}\n"
                    rel_text += f"   - Connected to: {rel['connected_node']['label']} ({rel['connected_node']['type']})"
                    if rel['connected_node'].get('description'):
                        desc = rel['connected_node']['description'][:100]
                        if len(rel['connected_node']['description']) > 100:
                            desc += "..."
                        rel_text += f"\n   - Description: {desc}"
                    if rel.get('sentence'):
                        sentence = rel['sentence'][:200]  # Limit sentence length
                        if len(rel['sentence']) > 200:
                            sentence += "..."
                        rel_text += f"\n   - Sentence: {sentence}"
                    neighborhood_text.append(rel_text)
                
                neighborhood_data = f"Total relationships: {edge_count}\n" + "\n".join(neighborhood_text)
                
                # Prepare data for the agent
                agent_input = {
                    "node_label": node_info.get('label', ''),
                    "node_type": node.node_type,
                    "node_category": getattr(node, 'category', ''),
                    "node_aliases": ", ".join(node_info.get('aliases', [])),
                    "node_attributes": str(node_info.get('attributes', {})),
                    "neighborhood_data": neighborhood_data,
                    "edge_count": str(edge_count),
                    "connection_to_jukka": connection_desc,
                    "jukka_distance": str(jukka_distance)
                }
                
                # Only add temporal fields for Event, State, or Goal nodes
                if node.node_type in ['Event', 'State', 'Goal']:
                    agent_input.update({
                        "start_date": node_info.get('start_date', ''),
                        "end_date": node_info.get('end_date', ''),
                        "valid_during": getattr(node, 'valid_during', '')
                    })
                
                # Call the agent
                response = cleanup_agent.action_handler(Message(agent_input=agent_input))
                
                # Calculate analysis duration
                analysis_duration = time.time() - analysis_start_time
                
                if response and response.data:
                    cleanup_result = response.data
                    suspect = cleanup_result.get('suspect', False)
                    
                    # Truncate very long agent responses to prevent database issues
                    # (This is a safety measure - the database should handle TEXT fields)
                    if 'suspect_reason' in cleanup_result and cleanup_result['suspect_reason']:
                        if len(cleanup_result['suspect_reason']) > 1000:
                            logger.warning(f"Truncating very long suspect_reason for {node.label}")
                            cleanup_result['suspect_reason'] = cleanup_result['suspect_reason'][:1000] + "..."
                    
                    if 'suggested_action' in cleanup_result and cleanup_result['suggested_action']:
                        if len(cleanup_result['suggested_action']) > 1000:
                            logger.warning(f"Truncating very long suggested_action for {node.label}")
                            cleanup_result['suggested_action'] = cleanup_result['suggested_action'][:1000] + "..."
                    
                    # Prepare node data for tracking
                    node_data = {
                        'node_id': str(node.id),
                        'label': node.label,
                        'type': node.node_type,
                        'node_type': node.node_type,
                        'category': getattr(node, 'category', ''),
                        'edge_count': edge_count,
                        'jukka_distance': jukka_distance
                    }
                    
                    # Mark node as analyzed in tracking system
                    mark_node_as_analyzed(
                        session, 
                        node_data, 
                        cleanup_result, 
                        analysis_duration=analysis_duration,
                        agent_version="kg_maintenance::node_cleanup"
                    )
                    
                    if suspect:
                        suspect_info = {
                            'node_id': str(node.id),
                            'label': node.label,
                            'type': node.node_type,
                            'node_type': node.node_type,
                            'category': getattr(node, 'category', ''),
                            'sentence': sentence,
                            'edge_count': edge_count,
                            'jukka_distance': jukka_distance,
                            'suspect_reason': cleanup_result.get('suspect_reason', ''),
                            'confidence': cleanup_result.get('confidence', 0.0),
                            'cleanup_priority': cleanup_result.get('cleanup_priority', 'none'),
                            'suggested_action': cleanup_result.get('suggested_action', '')
                        }
                        suspect_nodes.append(suspect_info)
                        logger.info(f" - FLAGGED AS SUSPECT: {node.label}")
                    else:
                        logger.info(f" - NOT suspect: {node.label}")
                    
                    processed_count += 1
                else:
                    error_count += 1
                    logger.error(f" - Failed to analyze {node.label}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing node {node.label}: {e}")
                try:
                    session.rollback()
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback session: {rollback_error}")
                    # Try to create a new session if rollback fails
                    try:
                        session.close()
                        session = get_session()
                    except Exception as session_error:
                        logger.error(f"Failed to create new session: {session_error}")
                        break  # Exit the loop if we can't recover
        
        # Get updated statistics
        final_stats = get_analysis_statistics(session)
        
        logger.info(f"Pipeline completed: {processed_count} processed, {len(suspect_nodes)} suspect, {error_count} errors, {skipped_count} skipped")
        logger.info(f"📊 Final coverage: {final_stats['analyzed_nodes']}/{final_stats['total_nodes']} nodes ({final_stats['coverage_percentage']:.1f}%)")
        
        # Sort suspect nodes by priority and confidence
        suspect_nodes.sort(key=lambda x: (
            {'high': 3, 'medium': 2, 'low': 1, 'none': 0}[x['cleanup_priority']], 
            x['confidence']
        ), reverse=True)
        
        return {
            "processed": processed_count,
            "suspect_count": len(suspect_nodes),
            "errors": error_count,
            "skipped": skipped_count,
            "suspect_nodes": suspect_nodes,
            "coverage": final_stats
        }
        
    finally:
        session.close()


def save_suspect_report(suspect_nodes: List[Dict], filename: str = None):
    """
    Save the suspect nodes report to a JSON file
    """
    if filename is None:
        from datetime import datetime
        filename = f"suspect_nodes_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = {
        "timestamp": str(datetime.now()),
        "total_suspect_nodes": len(suspect_nodes),
        "suspect_nodes": suspect_nodes
    }
    
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Suspect nodes report saved to {filename}")
    return filename


def print_suspect_summary(suspect_nodes: List[Dict]):
    """
    Print a summary of suspect nodes
    """
    print(f"\n🔍 SUSPECT NODES SUMMARY")
    print(f"=" * 50)
    print(f"Total suspect nodes: {len(suspect_nodes)}")
    
    if not suspect_nodes:
        print("No suspect nodes found! 🎉")
        return
    
    # Group by priority
    by_priority = defaultdict(list)
    for node in suspect_nodes:
        by_priority[node['cleanup_priority']].append(node)
    
    for priority in ['high', 'medium', 'low']:
        nodes = by_priority[priority]
        if nodes:
            print(f"\n{priority.upper()} PRIORITY ({len(nodes)} nodes):")
            for node in nodes[:10]:  # Show first 10
                print(f"  • {node['label']} ({node['type']}) - {node['jukka_distance']} hops from Jukka")
                print(f"    Reason: {node['suspect_reason'][:100]}...")
                if len(nodes) > 10:
                    print(f"    ... and {len(nodes) - 10} more")
    
    # Show some statistics
    distances = [n['jukka_distance'] for n in suspect_nodes]
    edge_counts = [n['edge_count'] for n in suspect_nodes]
    
    print(f"\n📊 STATISTICS:")
    print(f"  Average distance from Jukka: {sum(distances)/len(distances):.1f} hops")
    print(f"  Average edge count: {sum(edge_counts)/len(edge_counts):.1f}")
    print(f"  Nodes 4+ hops from Jukka: {sum(1 for d in distances if d >= 4)}")
    print(f"  Nodes with 0-1 edges: {sum(1 for e in edge_counts if e <= 1)}")


if __name__ == "__main__":
    import app.assistant.tests.test_setup # This is just run for the import
    from datetime import datetime
    
    print("🔍 Running Node Cleanup Pipeline...")
    print("=" * 50)
    
    # Show current analysis coverage
    session = get_session()
    try:
        initialize_node_analysis_tracking_db()
        stats = get_analysis_statistics(session)
        print(f"📊 Current coverage: {stats['analyzed_nodes']}/{stats['total_nodes']} nodes ({stats['coverage_percentage']:.1f}%)")
        print(f"📊 Suspect nodes found so far: {stats['suspect_nodes']}")
        print(f"📊 Recent analysis (24h): {stats['recent_analysis_24h']} nodes")
    finally:
        session.close()
    
    print("\n🔧 Choose processing mode:")
    print("   1. Process only unanalyzed nodes (default)")
    print("   2. Force reanalyze all nodes")
    print("   3. Process all nodes (legacy mode)")
    
    # For now, default to processing only unanalyzed nodes
    try:
        print("\n🚀 Processing unanalyzed nodes...")
        result = run_node_cleanup_pipeline(skip_analyzed=True, force_reanalyze=False)
        
        # Print summary
        print_suspect_summary(result['suspect_nodes'])
        
        # Save report
        filename = save_suspect_report(result['suspect_nodes'])
        print(f"\n📄 Detailed report saved to: {filename}")
        
        print(f"\n✅ Pipeline completed!")
        print(f"  Processed: {result['processed']} nodes")
        print(f"  Suspect: {result['suspect_count']} nodes")
        print(f"  Errors: {result['errors']} nodes")
        print(f"  Skipped: {result['skipped']} nodes")
        
        if 'coverage' in result:
            coverage = result['coverage']
            print(f"  Coverage: {coverage['analyzed_nodes']}/{coverage['total_nodes']} nodes ({coverage['coverage_percentage']:.1f}%)")
        
    except Exception as e:
        print(f"❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🏁 Knowledge Graph Pipeline execution finished")
