"""
Duplicate Analysis Pipeline
Uses the duplicate detector agent to analyze and prioritize duplicate nodes for cleanup
"""

import json
import time
import glob
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge

from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

# Import the tracking system for table initialization
from app.models.duplicate_node_tracking import (
    initialize_duplicate_node_tracking_db
)

logger = get_logger(__name__)


def get_duplicate_groups_from_json_report(session: Session, limit: int = None) -> List[List[str]]:
    """
    Get duplicate groups from the JSON report - expects simple format with just node ID groups
    Returns list of duplicate groups, each group containing list of node IDs
    """
    # Try to find any duplicate report
    reports = []
    reports.extend(glob.glob("random_sampling_results_*.json"))
    reports.extend(glob.glob("duplicate_nodes_report_*.json"))
    
    if not reports:
        raise FileNotFoundError("No duplicate nodes report found. Run random_sampling_duplicate_detector or node_deduplication_pipeline first.")
    
    # Get the most recent one
    reports.sort(reverse=True)
    filename = reports[0]
    logger.info(f"Using most recent report: {filename}")
    
    with open(filename, 'r') as f:
        report = json.load(f)
    
    # Handle simple format: duplicate_groups is list of lists of node IDs
    if 'duplicate_groups' in report and isinstance(report['duplicate_groups'], list):
        duplicate_groups = []
        for group in report['duplicate_groups']:
            if isinstance(group, list) and len(group) >= 2:
                # Validate that all items are strings (UUIDs)
                if all(isinstance(node_id, str) for node_id in group):
                    duplicate_groups.append(group)
        
        logger.info(f"Loaded {len(duplicate_groups)} duplicate groups from {filename}")
        return duplicate_groups[:limit] if limit else duplicate_groups
    
    # Handle legacy format (fallback)
    logger.info(f"Legacy format detected, attempting to parse...")
    
    if 'all_potential_duplicates' in report:
        # Old random sampling format
        duplicate_groups = []
        for group_data in report['all_potential_duplicates']:
            if 'node_ids' in group_data and len(group_data['node_ids']) >= 2:
                duplicate_groups.append(group_data['node_ids'])
        
        logger.info(f"Converted {len(duplicate_groups)} groups from legacy format")
        return duplicate_groups[:limit] if limit else duplicate_groups
    
    elif 'duplicate_results' in report:
        # Old deduplication format
        # Group by label and type, extract node IDs
        duplicate_groups = {}
        for result in report['duplicate_results']:
            node_id = result['node_id']
            label = result['label']
            node_type = result['type']
            
            group_key = f"{label}_{node_type}"
            if group_key not in duplicate_groups:
                duplicate_groups[group_key] = []
            duplicate_groups[group_key].append(node_id)
        
        # Convert to list format
        result_groups = []
        for group in duplicate_groups.values():
            if len(group) >= 2:
                result_groups.append(group)
        
        logger.info(f"Converted {len(result_groups)} groups from legacy format")
        return result_groups[:limit] if limit else result_groups
    
    else:
        raise ValueError(f"Unknown report format in {filename}")


def find_similar_nodes_for_analysis(session: Session, node_id: str) -> List[Dict]:
    """
    Find nodes similar to the given node for duplicate analysis
    Returns list of node info dictionaries
    """
    # Get the target node
    target_node = session.query(Node).filter(Node.id == node_id).first()
    if not target_node:
        return []
    
    # Find similar nodes based on label similarity and type
    similar_nodes = []
    
    # Add the target node
    similar_nodes.append(get_node_analysis_info(session, target_node))
    
    # Find nodes with similar labels
    similar_labels = find_nodes_with_similar_labels(session, target_node.label, target_node.node_type)
    
    for similar_node in similar_labels:
        if str(similar_node.id) != node_id:
            similar_nodes.append(get_node_analysis_info(session, similar_node))
    
    return similar_nodes


def find_nodes_with_similar_labels(session: Session, label: str, node_type: str) -> List[Node]:
    """
    Find nodes with similar labels and same type
    """
    # Simple similarity: exact match, contains, or contained in
    similar_nodes = []
    
    # Exact match with same type
    exact_matches = session.query(Node).filter(
        Node.label == label,
        Node.node_type == node_type
    ).all()
    similar_nodes.extend(exact_matches)
    
    # Label contains the target label
    contains_matches = session.query(Node).filter(
        Node.label.contains(label),
        Node.node_type == node_type,
        Node.label != label
    ).all()
    similar_nodes.extend(contains_matches)
    
    # Target label contains this label
    contained_matches = session.query(Node).filter(
        label.contains(Node.label),
        Node.node_type == node_type,
        Node.label != label
    ).all()
    similar_nodes.extend(contained_matches)
    
    return similar_nodes


def get_neighborhood_sample(session: Session, node_id: str, max_nodes: int = 50) -> List[Dict]:
    """
    Get a sample of neighborhood nodes (up to max_nodes) to avoid huge neighborhoods
    """
    # Get edges connected to this node
    edges = session.query(Edge).filter(
        (Edge.source_id == node_id) | (Edge.target_id == node_id)
    ).limit(max_nodes * 2).all()  # Get more edges to have variety
    
    neighborhood_nodes = []
    seen_nodes = set()
    
    for edge in edges:
        # Get the other node (not the current one)
        other_node_id = edge.target_id if edge.source_id == node_id else edge.source_id
        
        if other_node_id and str(other_node_id) not in seen_nodes:
            other_node = session.query(Node).filter(Node.id == other_node_id).first()
            if other_node:
                neighborhood_nodes.append({
                    'node_id': str(other_node.id),
                    'label': other_node.label,
                    'node_type': other_node.node_type,
                    'edge_type': edge.relationship_type,
                    'direction': 'outgoing' if edge.source_id == node_id else 'incoming'
                })
                seen_nodes.add(str(other_node.id))
                
                if len(neighborhood_nodes) >= max_nodes:
                    break
    
    return neighborhood_nodes


def get_node_analysis_info(session: Session, node_id: str) -> Dict:
    """
    Get comprehensive node information for analysis - fetches fresh data to avoid bias
    """
    # Get the node from the database
    node = session.query(Node).filter(Node.id == node_id).first()
    if not node:
        return None
    
    # Build context from available sources
    context_parts = []
    
    # Add node description if available
    if node.description:
        context_parts.append(node.description)
    
    # Add node label and aliases
    context_parts.append(node.label)
    if node.aliases:
        context_parts.extend(node.aliases)
    
    # Add hash tags for categorical context
    if node.hash_tags:
        context_parts.extend(node.hash_tags)
    
    # Get edge sentences for relationship context
    edge_sentences = session.query(Edge.sentence).filter(
        (Edge.source_id == node.id) | (Edge.target_id == node.id)
    ).filter(Edge.sentence.isnot(None)).limit(5).all()
    
    for sentence_tuple in edge_sentences:
        if sentence_tuple[0]:  # sentence is not None
            context_parts.append(sentence_tuple[0])
    
    # Combine all context
    context = " ".join(context_parts)
    
    # Sample neighborhood (up to 50 nodes) to avoid huge neighborhoods
    neighborhood_sample = get_neighborhood_sample(session, node_id, max_nodes=50)
    
    # Count edges
    edge_count = session.query(Edge).filter(
        (Edge.source_id == node.id) | (Edge.target_id == node.id)
    ).count()
    
    return {
        'node_id': str(node.id),
        'label': node.label,
        'node_type': node.node_type,
        'category': node.category,
        'description': node.description,
        'aliases': node.aliases or [],
        'hash_tags': node.hash_tags or [],
        'context': context,
        'attributes': node.attributes or {},
        'edge_count': edge_count,
        'neighborhood_sample': neighborhood_sample,
        'created_at': str(node.created_at) if node.created_at else None,
        'updated_at': str(node.updated_at) if node.updated_at else None
    }


def run_duplicate_analysis_pipeline(max_groups: int = None, force_reanalyze: bool = False):
    """
    Main pipeline function to analyze duplicate nodes using the duplicate detector agent
    
    Args:
        max_groups: Maximum number of duplicate groups to analyze
        force_reanalyze: If True, reanalyze all groups regardless of previous analysis
    """
    session = get_session()
    
    try:
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        logger.info(f"🔍 Connecting to database: {db_uri}")
        
        # Initialize the tracking table if it doesn't exist
        initialize_duplicate_node_tracking_db()
        
        # Create the duplicate detector agent
        duplicate_detector_agent = DI.agent_factory.create_agent("kg_maintenance::duplicate_detector")
        
        # Get duplicate groups for analysis
        logger.info("🔍 Identifying duplicate groups for analysis...")
        duplicate_groups = get_duplicate_groups_from_json_report(session, max_groups)
        logger.info(f"📋 Found {len(duplicate_groups)} duplicate groups to analyze")
        
        if not duplicate_groups:
            logger.info("✅ No duplicate groups found for analysis!")
            return
        
        # Process each duplicate group
        processed_count = 0
        error_count = 0
        analysis_results = []
        
        for group_idx, group in enumerate(duplicate_groups, 1):
            try:
                logger.info(f"🔍 Analyzing duplicate group {group_idx}/{len(duplicate_groups)}")
                logger.info(f"   Node IDs: {group[:3]}{'...' if len(group) > 3 else ''}")
                
                # Fetch fresh, unbiased node data from the database
                fresh_node_data = []
                for node_id in group:
                    fresh_node = get_node_analysis_info(session, node_id)
                    if fresh_node:
                        fresh_node_data.append(fresh_node)
                
                if len(fresh_node_data) < 2:
                    logger.warning(f"   ⚠️  Skipping group {group_idx}: insufficient fresh data")
                    continue
                
                # Prepare input for the duplicate detector agent
                duplicate_group_data = json.dumps(fresh_node_data, indent=2)
                analysis_context = {
                    'group_size': len(fresh_node_data),
                    'group_index': group_idx,
                    'total_groups': len(duplicate_groups),
                    'analysis_timestamp': time.time()
                }
                
                agent_input = {
                    'duplicate_group_data': duplicate_group_data,
                    'analysis_context': json.dumps(analysis_context, indent=2)
                }
                
                # Get agent analysis
                start_time = time.time()
                agent_response = duplicate_detector_agent.action_handler(Message(agent_input=agent_input))
                analysis_duration = time.time() - start_time
                
                analysis_result = agent_response.data or {}
                
                # Validate the response
                if not isinstance(analysis_result, dict):
                    logger.warning(f"   ⚠️  Invalid agent response format: {type(analysis_result)}")
                    analysis_result = {
                        'merge_actions': [],
                        'total_merges': 0
                    }
                
                # Extract merge actions from the new format
                merge_actions = analysis_result.get('merge_actions', [])
                total_merges = analysis_result.get('total_merges', len(merge_actions))
                
                # Log results
                if merge_actions:
                    logger.info(f"   ✅ MERGES DETECTED: {total_merges} merge actions")
                    for i, action in enumerate(merge_actions):
                        merge_ids = action.get('merge', [])
                        labels = action.get('labels', [])
                        reason = action.get('reason', 'No reason provided')
                        logger.info(f"      Merge {i+1}: {len(merge_ids)} nodes - {reason}")
                        logger.info(f"         Labels: {labels}")
                        logger.info(f"         Node IDs: {merge_ids}")
                else:
                    logger.info(f"   ❌ NO MERGES DETECTED: All nodes are unique")
                
                analysis_results.append({
                    'group_index': group_idx,
                    'nodes': [node['label'] for node in fresh_node_data],
                    'analysis_result': analysis_result
                })
                
                processed_count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(f"   ❌ Error analyzing group {group_idx}: {e}")
                session.rollback()
        
        logger.info(f"Pipeline completed: {processed_count} groups processed, {error_count} errors")
        
        # Save detailed analysis report
        save_analysis_report(analysis_results)
        
        return {
            'groups_processed': processed_count,
            'errors': error_count,
            'analysis_results': analysis_results
        }
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        session.rollback()
        raise e
    finally:
        session.close()


def save_analysis_report(analysis_results: List[Dict], filename: str = None) -> str:
    """
    Save the analysis results to a JSON file
    """
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"duplicate_analysis_report_{timestamp}.json"
    
    report_data = {
        'timestamp': datetime.now().isoformat(),
        'total_groups_analyzed': len(analysis_results),
        'analysis_results': analysis_results
    }
    
    # Ensure dedupe_logs directory exists
    import os
    os.makedirs('dedupe_logs', exist_ok=True)
    
    # Save to dedupe_logs subfolder
    filepath = os.path.join('dedupe_logs', filename)
    with open(filepath, 'w') as f:
        json.dump(report_data, f, indent=2)
    
    logger.info(f"📄 Detailed analysis report saved to: {filepath}")
    return filename


def print_analysis_summary(analysis_results: List[Dict]):
    """
    Print a summary of the duplicate analysis results
    """
    print(f"\n🔍 DUPLICATE ANALYSIS SUMMARY")
    print(f"=" * 50)
    print(f"Total groups analyzed: {len(analysis_results)}")
    
    if not analysis_results:
        print("No groups analyzed! 🎉")
        return
    
    # Group by merge status
    groups_with_merges = []
    groups_without_merges = []
    
    for result in analysis_results:
        merge_actions = result['analysis_result'].get('merge_actions', [])
        if merge_actions:
            groups_with_merges.append(result)
        else:
            groups_without_merges.append(result)
    
    # Show merge breakdown
    print(f"\n🔗 GROUPS WITH MERGES ({len(groups_with_merges)} groups):")
    for group in groups_with_merges[:5]:  # Show first 5
        nodes = group['nodes']
        merge_actions = group['analysis_result'].get('merge_actions', [])
        total_merges = len(merge_actions)
        print(f"  • {', '.join(nodes)} - {total_merges} merge actions")
        for i, action in enumerate(merge_actions[:2]):  # Show first 2 merge actions
            merge_ids = action.get('merge', [])
            reason = action.get('reason', 'No reason')
            print(f"    Merge {i+1}: {len(merge_ids)} nodes - {reason}")
    
    if len(groups_with_merges) > 5:
        print(f"    ... and {len(groups_with_merges) - 5} more groups with merges")
    
    print(f"\n✅ UNIQUE GROUPS ({len(groups_without_merges)} groups):")
    print(f"  All nodes in these groups are unique and should not be merged")
    
    # Show merge statistics
    total_merge_actions = sum(len(r['analysis_result'].get('merge_actions', [])) for r in analysis_results)
    total_nodes_to_merge = sum(
        len(action.get('merge', [])) 
        for r in analysis_results 
        for action in r['analysis_result'].get('merge_actions', [])
    )
    
    print(f"\n📊 MERGE STATISTICS:")
    print(f"  Total merge actions: {total_merge_actions}")
    print(f"  Total nodes to merge: {total_nodes_to_merge}")
    print(f"  Groups with merges: {len(groups_with_merges)}")
    print(f"  Groups without merges: {len(groups_without_merges)}")


if __name__ == "__main__":
    import app.assistant.tests.test_setup
    
    print("🔍 Running Duplicate Analysis Pipeline...")
    print("=" * 50)
    
    try:
        results = run_duplicate_analysis_pipeline(max_groups=50)  # Start with 50 groups
        
        if results:
            print_analysis_summary(results['analysis_results'])
            print(f"\n✅ Pipeline completed successfully!")
        else:
            print("❌ Pipeline failed to return results")
            
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
