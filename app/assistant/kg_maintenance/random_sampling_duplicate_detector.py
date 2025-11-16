"""
Random Sampling Duplicate Detector
Efficiently finds potential duplicates by sampling random node labels and using AI agent
"""

import json
import random
import time
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def get_random_node_sample(session: Session, sample_size: int = 1000, excluded_pairs: set = None) -> List[Dict]:
    """
    Get a weighted random sample of node labels with enum IDs
    Weights nodes by their incoming edge count (more connected = higher weight)
    Avoids sampling nodes that have already been analyzed together in previous batches
    
    Args:
        session: Database session
        sample_size: Number of nodes to sample
        excluded_pairs: Set of (node_id1, node_id2) tuples that have already been analyzed together
    
    Returns:
        List of {enum_id, label, node_type, edge_count} dictionaries
    """
    if excluded_pairs is None:
        excluded_pairs = set()
    
    # Get total count of nodes with labels
    total_nodes = session.query(Node).filter(Node.label.isnot(None)).count()
    
    if total_nodes == 0:
        logger.warning("No nodes with labels found in database")
        return []
    
    # Get nodes with their incoming edge counts
    # Using LEFT JOIN to include nodes with 0 incoming edges
    print(f"🔍 DEBUG: About to query Node.node_type from {Node.__tablename__}")
    try:
        nodes_with_edge_counts = session.query(
            Node.id,
            Node.label, 
            Node.node_type,
            func.count(Edge.id).label('incoming_edge_count')
        ).outerjoin(
            Edge, Node.id == Edge.target_id
        ).filter(
            Node.label.isnot(None)
        ).group_by(
            Node.id, Node.label, Node.node_type
        ).all()
        print(f"🔍 DEBUG: Query successful, got {len(nodes_with_edge_counts)} results")
    except Exception as e:
        print(f"🔍 DEBUG: Query failed with error: {e}")
        print(f"🔍 DEBUG: Node model table: {Node.__tablename__}")
        print(f"🔍 DEBUG: Node model columns: {[col.name for col in Node.__table__.columns]}")
        raise
    
    if not nodes_with_edge_counts:
        logger.warning("No nodes with edge counts found")
        return []
    
    # Convert to list of dictionaries with weights
    weighted_nodes = []
    print(f"🔍 DEBUG: Processing {len(nodes_with_edge_counts)} nodes from query results")
    for i, (node_id, label, node_type, edge_count) in enumerate(nodes_with_edge_counts):
        print(f"🔍 DEBUG: Node {i+1}: id={node_id}, label={label}, node_type={node_type}, edge_count={edge_count}")
        # Add 1 to edge count to ensure all nodes have at least weight 1
        weight = max(1, edge_count + 1)
        weighted_nodes.append({
            'node_id': str(node_id),
            'label': label,
            'node_type': node_type,
            'edge_count': edge_count,
            'weight': weight
        })
    
    # Filter out nodes that would create excluded pairs
    if excluded_pairs:
        # Create a set of node IDs that are in excluded pairs for faster lookup
        excluded_node_ids = set()
        for node_id1, node_id2 in excluded_pairs:
            excluded_node_ids.add(node_id1)
            excluded_node_ids.add(node_id2)
        
        # Filter out nodes that are in excluded pairs
        filtered_nodes = [node for node in weighted_nodes if node['node_id'] not in excluded_node_ids]
        
        if len(filtered_nodes) < sample_size:
            logger.warning(f"Only {len(filtered_nodes)} nodes available after filtering excluded pairs (need {sample_size})")
            # If we don't have enough nodes, we'll work with what we have
            weighted_nodes = filtered_nodes
        else:
            weighted_nodes = filtered_nodes
            logger.info(f"Filtered out {len(excluded_node_ids)} nodes that were in excluded pairs")
    
    # Weighted random sampling WITHOUT replacement
    import random
    total_weight = sum(node['weight'] for node in weighted_nodes)
    
    if total_weight == 0:
        logger.warning("Total weight is 0, falling back to uniform sampling")
        # Fallback to uniform random sampling
        random_nodes = random.sample(weighted_nodes, min(sample_size, len(weighted_nodes)))
    else:
        # Weighted sampling WITHOUT replacement: each node can only be selected once
        random_nodes = []
        available_nodes = weighted_nodes.copy()
        available_weight = total_weight
        
        for _ in range(min(sample_size, len(weighted_nodes))):
            if not available_nodes:
                break
                
            # Pick a random weight value
            target_weight = random.uniform(0, available_weight)
            current_weight = 0
            
            # Find the node corresponding to this weight
            selected_node = None
            for i, node in enumerate(available_nodes):
                current_weight += node['weight']
                if current_weight >= target_weight:
                    selected_node = node
                    # Remove the selected node from available nodes
                    available_nodes.pop(i)
                    available_weight -= node['weight']
                    break
            
            if selected_node:
                random_nodes.append(selected_node)
    
    # Assign enum IDs and ensure no duplicates
    sample_data = []
    seen_node_ids = set()
    print(f"🔍 DEBUG: Converting {len(random_nodes)} random nodes to sample format")
    
    for i, node in enumerate(random_nodes, 1):
        print(f"🔍 DEBUG: Converting node {i}: {node}")
        
        # Safety check: ensure no duplicate node IDs
        if node['node_id'] in seen_node_ids:
            print(f"🔍 DEBUG: WARNING - Duplicate node_id detected: {node['node_id']}, skipping")
            continue
            
        seen_node_ids.add(node['node_id'])
        sample_data.append({
            'enum_id': i,
            'node_id': node['node_id'],
            'label': node['label'],
            'node_type': node['node_type'],
            'edge_count': node['edge_count']
        })
    
    print(f"🔍 DEBUG: Sample data created: {len(sample_data)} items (after deduplication)")
    
    # Log statistics about the sample
    avg_edge_count = sum(node['edge_count'] for node in sample_data) / len(sample_data)
    max_edge_count = max(node['edge_count'] for node in sample_data)
    nodes_with_edges = sum(1 for node in sample_data if node['edge_count'] > 0)
    
    logger.info(f"Sampled {len(sample_data)} weighted random nodes from {total_nodes} total nodes")
    logger.info(f"Sample stats: avg_edge_count={avg_edge_count:.1f}, max_edge_count={max_edge_count}, nodes_with_edges={nodes_with_edges}")
    
    return sample_data


def create_agent_input(sample_data: List[Dict], batch_number: int) -> Dict:
    """
    Create input for the duplicate detection agent
    """
    print(f"🔍 DEBUG: create_agent_input called with {len(sample_data)} nodes")
    print(f"🔍 DEBUG: First node keys: {list(sample_data[0].keys()) if sample_data else 'No data'}")
    
    # Format the sample data for the agent with edge count information
    formatted_nodes = []
    for i, node in enumerate(sample_data):
        print(f"🔍 DEBUG: Processing node {i+1}: {node}")
        if 'node_type' not in node:
            print(f"🔍 DEBUG: ERROR - node_type key missing from node: {node}")
            raise KeyError(f"node_type key missing from node: {node}")
        edge_info = f"({node['edge_count']} edges)" if node['edge_count'] > 0 else "(no edges)"
        formatted_nodes.append(f"{node['enum_id']}: {node['label']} ({node['node_type']}) {edge_info}")
    
    nodes_text = "\n".join(formatted_nodes)
    
    agent_input = {
        'batch_number': batch_number,
        'total_nodes_in_sample': len(sample_data),
        'node_list': nodes_text,
        'instructions': """
        Review this list of nodes and identify which ones might be duplicates.
        The edge count shows how many connections each node has - nodes with more edges are more important.
        
        Look for:
        - Similar names (e.g., "jukka" vs "jukka_virtanen")
        - Abbreviations (e.g., "nyc" vs "new_york")
        - Variations (e.g., "john" vs "john_doe")
        - Same concepts with different labels
        
        When merging duplicates, prefer to keep the node with more edges as the primary node.
        Return ONLY the enum IDs of nodes that look like potential duplicates.
        Group related nodes together.
        """
    }
    
    return agent_input


def parse_agent_response(agent_response: str) -> List[List[int]]:
    """
    Parse the agent's response to extract enum ID groups
    Returns list of groups, each group contains enum IDs of potentially duplicate nodes
    """
    try:
        # Try to parse as structured data first
        if hasattr(agent_response, 'data') and agent_response.data:
            data = agent_response.data
            if isinstance(data, dict) and 'duplicate_groups' in data:
                return data['duplicate_groups']
        
        # Fallback: try to extract from text response
        response_text = str(agent_response)
        
        # Look for patterns like "Group 1: 1, 45, 234" or "1, 45, 234"
        import re
        number_patterns = re.findall(r'\d+(?:,\s*\d+)*', response_text)
        
        duplicate_groups = []
        for pattern in number_patterns:
            # Extract individual numbers
            numbers = [int(n.strip()) for n in pattern.split(',')]
            if len(numbers) >= 2:  # Need at least 2 nodes for a duplicate group
                duplicate_groups.append(numbers)
        
        logger.info(f"Parsed {len(duplicate_groups)} potential duplicate groups from agent response")
        return duplicate_groups
        
    except Exception as e:
        logger.error(f"Failed to parse agent response: {e}")
        return []


def fetch_nodes_by_labels(session: Session, labels: List[str]) -> List[Node]:
    """
    Fetch actual Node objects from database by their labels
    """
    nodes = session.query(Node).filter(Node.label.in_(labels)).all()
    logger.info(f"Fetched {len(nodes)} nodes for labels: {labels[:5]}...")
    return nodes


def extract_node_pairs_from_sample(sample_data: List[Dict]) -> set:
    """
    Extract all possible node pairs from a sample for tracking
    Returns set of (node_id1, node_id2) tuples where node_id1 < node_id2 (for consistency)
    """
    node_pairs = set()
    node_ids = [node['node_id'] for node in sample_data]
    
    # Create all possible pairs
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            node_id1, node_id2 = node_ids[i], node_ids[j]
            # Ensure consistent ordering (smaller ID first)
            if node_id1 < node_id2:
                node_pairs.add((node_id1, node_id2))
            else:
                node_pairs.add((node_id2, node_id1))
    
    logger.info(f"Extracted {len(node_pairs)} node pairs from sample of {len(node_ids)} nodes")
    return node_pairs


def run_random_sampling_pipeline(num_batches: int = 10, sample_size: int = 1000):
    """
    Main pipeline function using random sampling approach
    
    Args:
        num_batches: Number of random samples to process
        sample_size: Number of nodes to sample per batch
    """
    session = get_session()
    
    try:
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        logger.info(f"🔍 Connecting to database: {db_uri}")
        
        # Create the random sampling duplicate detector agent
        duplicate_detector_agent = DI.agent_factory.create_agent("kg_maintenance::duplicate_detector_random_sampling")
        
        all_potential_duplicates = []
        batch_results = []
        excluded_pairs = set()  # Track node pairs that have already been analyzed together
        
        for batch_num in range(1, num_batches + 1):
            logger.info(f"🔍 Processing batch {batch_num}/{num_batches}")
            logger.info(f"📊 Excluded pairs so far: {len(excluded_pairs)}")
            
            try:
                print(f"🔍 DEBUG: Starting batch {batch_num} - getting random sample...")
                # Get random sample, excluding nodes that have already been analyzed together
                sample_data = get_random_node_sample(session, sample_size, excluded_pairs)
                print(f"🔍 DEBUG: Got sample data: {len(sample_data)} nodes")
                if not sample_data:
                    logger.warning(f"Batch {batch_num}: No sample data available")
                    continue
                
                # Extract node pairs from this sample and add to excluded pairs
                current_sample_pairs = extract_node_pairs_from_sample(sample_data)
                excluded_pairs.update(current_sample_pairs)
                
                # Create agent input
                agent_input = create_agent_input(sample_data, batch_num)
                
                # Get agent analysis
                start_time = time.time()
                agent_response = duplicate_detector_agent.action_handler(Message(agent_input=agent_input))
                analysis_duration = time.time() - start_time
                
                logger.info(f"Batch {batch_num}: Agent analysis completed in {analysis_duration:.2f}s")
                
                # Parse agent response
                duplicate_groups = parse_agent_response(agent_response)
                
                # Convert enum IDs back to actual labels and UUIDs
                enum_to_label = {node['enum_id']: node['label'] for node in sample_data}
                enum_to_uuid = {node['enum_id']: node['node_id'] for node in sample_data}
                enum_to_edge_count = {node['enum_id']: node['edge_count'] for node in sample_data}
                
                batch_duplicates = []
                for group in duplicate_groups:
                    labels = [enum_to_label.get(enum_id, f"unknown_{enum_id}") for enum_id in group]
                    node_ids = [enum_to_uuid.get(enum_id, f"unknown_{enum_id}") for enum_id in group]
                    edge_counts = [enum_to_edge_count.get(enum_id, 0) for enum_id in group]
                    batch_duplicates.append({
                        'node_ids': node_ids,
                        'labels': labels,
                        'edge_counts': edge_counts,
                        'batch_number': batch_num
                    })
                
                batch_results.append({
                    'batch_number': batch_num,
                    'sample_size': len(sample_data),
                    'duplicate_groups_found': len(duplicate_groups),
                    'duplicate_groups': batch_duplicates
                })
                
                all_potential_duplicates.extend(batch_duplicates)
                
                # Log what was found for immediate visibility
                if duplicate_groups:
                    logger.info(f"Batch {batch_num} - Duplicate groups found:")
                    for i, group in enumerate(batch_duplicates, 1):
                        labels = group['labels']
                        node_ids = group['node_ids']
                        edge_counts = group['edge_counts']
                        edge_info = f" (edges: {edge_counts})" if edge_counts else ""
                        logger.info(f"  Group {i}: {', '.join(labels)}{edge_info} (Node IDs: {node_ids[:2]}...)")
                else:
                    logger.info(f"Batch {batch_num}: No potential duplicates found")
                
                # Show running total
                logger.info(f"Running total: {len(all_potential_duplicates)} duplicate groups found so far")
                logger.info(f"📊 Total excluded pairs: {len(excluded_pairs)} (avoiding redundant analysis)")
                
            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}")
                continue
        
        # Save results in simple format - just groups of node IDs
        results = {
            'timestamp': time.time(),
            'total_batches': num_batches,
            'sample_size_per_batch': sample_size,
            'total_duplicate_groups_found': len(all_potential_duplicates),
            'duplicate_groups': []
        }
        
        # Convert to simple format: just groups of node IDs
        for group_data in all_potential_duplicates:
            if 'node_ids' in group_data and len(group_data['node_ids']) >= 2:
                results['duplicate_groups'].append(group_data['node_ids'])
        
        save_sampling_results(results)
        save_excluded_pairs(excluded_pairs)
        
        logger.info(f"Pipeline completed: {len(all_potential_duplicates)} potential duplicate groups found across {num_batches} batches")
        logger.info(f"📊 Exclusion effectiveness: {len(excluded_pairs)} node pairs avoided redundant analysis")
        
        return results
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        session.rollback()
        raise e
    finally:
        session.close()


def save_sampling_results(results: Dict, filename: str = None) -> str:
    """
    Save the random sampling results to a JSON file
    """
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"random_sampling_results_{timestamp}.json"
    
    # Ensure dedupe_logs directory exists
    import os
    os.makedirs('dedupe_logs', exist_ok=True)
    
    # Save to dedupe_logs subfolder
    filepath = os.path.join('dedupe_logs', filename)
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"📄 Random sampling results saved to: {filepath}")
    return filename


def save_excluded_pairs(excluded_pairs: set, filename: str = None) -> str:
    """
    Save the excluded pairs to a JSON file for persistence across runs
    """
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"excluded_pairs_{timestamp}.json"
    
    # Convert set of tuples to list of lists for JSON serialization
    excluded_pairs_list = [list(pair) for pair in excluded_pairs]
    
    data = {
        'timestamp': time.time(),
        'total_excluded_pairs': len(excluded_pairs),
        'excluded_pairs': excluded_pairs_list
    }
    
    # Ensure dedupe_logs directory exists
    import os
    os.makedirs('dedupe_logs', exist_ok=True)
    
    # Save to dedupe_logs subfolder
    filepath = os.path.join('dedupe_logs', filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"📄 Excluded pairs saved to: {filepath}")
    return filename


def load_excluded_pairs(filename: str) -> set:
    """
    Load excluded pairs from a JSON file
    """
    try:
        # Try to load from dedupe_logs subfolder first, then current directory
        import os
        filepath = os.path.join('dedupe_logs', filename)
        if not os.path.exists(filepath):
            filepath = filename  # Fallback to current directory
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Convert list of lists back to set of tuples
        excluded_pairs = set(tuple(pair) for pair in data['excluded_pairs'])
        logger.info(f"📄 Loaded {len(excluded_pairs)} excluded pairs from: {filepath}")
        return excluded_pairs
    except Exception as e:
        logger.warning(f"Failed to load excluded pairs from {filepath}: {e}")
        return set()


def print_sampling_summary(results: Dict):
    """
    Print a summary of the random sampling results
    """
    print(f"\n🔍 RANDOM SAMPLING SUMMARY")
    print(f"=" * 50)
    print(f"Total batches processed: {results['total_batches']}")
    print(f"Sample size per batch: {results['sample_size_per_batch']}")
    print(f"Total potential duplicate groups: {results['total_duplicate_groups_found']}")
    
    if not results['duplicate_groups']:
        print("No potential duplicates found! 🎉")
        return
    
    # Show sample of duplicate groups
    print(f"\n📊 Sample of duplicate groups found:")
    for i, group in enumerate(results['duplicate_groups'][:10]):  # Show first 10
        if len(group) >= 2:
            print(f"  Group {i+1}: {len(group)} nodes (Node IDs: {group[:2]}...)")
    
    if len(results['duplicate_groups']) > 10:
        print(f"  ... and {len(results['duplicate_groups']) - 10} more groups")
    
    print(f"\n💾 Results saved to JSON file for further analysis")


if __name__ == "__main__":
    import app.assistant.tests.test_setup
    
    print("🔍 Running Random Sampling Duplicate Detector...")
    print("=" * 50)
    
    try:
        results = run_random_sampling_pipeline(
            num_batches=20,  # Process 10 batches
            sample_size=300  # 1000 nodes per batch
        )
        
        if results:
            print_sampling_summary(results)
            print(f"\n✅ Pipeline completed successfully!")
            print(f"  Total duplicate groups found: {results['total_duplicate_groups_found']}")
        else:
            print("❌ Pipeline failed to return results")
            
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🏁 Random Sampling Duplicate Detector finished")
