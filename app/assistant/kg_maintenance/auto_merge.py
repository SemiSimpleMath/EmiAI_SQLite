#!/usr/bin/env python3
"""
Auto-Merge High Confidence Duplicates
Automatically merges duplicate nodes based on agent analysis results
"""

import json
import glob
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
# Note: merge_nodes import removed - now using unified merge function from knowledge_graph_utils
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def load_analysis_results(filename: str = None) -> Dict:
    """
    Load duplicate analysis results from JSON file
    """
    if not filename:
        # Find the most recent analysis report
        reports = glob.glob("duplicate_analysis_report_*.json")
        if not reports:
            raise FileNotFoundError("No duplicate analysis report found. Run duplicate_analysis_pipeline first.")
        
        reports.sort(reverse=True)
        filename = reports[0]
        logger.info(f"Using most recent analysis report: {filename}")
    
    with open(filename, 'r') as f:
        results = json.load(f)
    
    logger.info(f"Loaded analysis report with {len(results['analysis_results'])} groups")
    return results


def extract_merge_actions(analysis_results: List[Dict]) -> List[Dict]:
    """
    Extract all merge actions from analysis results
    """
    merge_actions = []
    
    for group in analysis_results:
        analysis_result = group.get('analysis_result', {})
        
        # Check if this is the new simplified format
        if 'merge_actions' in analysis_result:
            for action in analysis_result['merge_actions']:
                if 'merge' in action and len(action['merge']) >= 2:
                    merge_actions.append({
                        'group_index': group['group_index'],
                        'all_nodes': action['merge'],  # All nodes to consider
                        'labels': action.get('labels', []),
                        'reason': action.get('reason', 'No reason given')
                    })
        
        # Handle legacy format for backward compatibility
        elif analysis_result.get('suggested_action') == 'merge' and analysis_result.get('confidence', 0) >= 0.8:
            # Extract from legacy format if possible
            if 'primary_node_id' in analysis_result:
                merge_actions.append({
                    'group_index': group['group_index'],
                    'all_nodes': group['nodes'],
                    'labels': group['nodes'],
                    'reason': 'Legacy format conversion'
                })
    
    return merge_actions


def validate_nodes_exist(session: Session, node_ids: List[str]) -> Dict[str, Node]:
    """
    Validate that all node IDs exist in the database
    Returns dict mapping node_id to Node object
    """
    nodes = {}
    for node_id in node_ids:
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            logger.warning(f"Node {node_id} not found in database")
            continue
        nodes[node_id] = node
    
    return nodes


def auto_merge_duplicates(dry_run: bool = True):
    """
    Automatically merge duplicate nodes based on agent analysis
    
    Args:
        dry_run: If True, only show what would be merged without actually merging
    """
    session = get_session()
    
    try:
        # Load analysis results
        analysis_results = load_analysis_results()
        
        # Extract merge actions
        merge_actions = extract_merge_actions(analysis_results['analysis_results'])
        
        logger.info(f"Found {len(merge_actions)} merge actions to process")
        
        if not merge_actions:
            logger.info("No merge actions to perform")
            return
        
        # Process each merge action
        successful_merges = 0
        failed_merges = 0
        
        for action in merge_actions:
            try:
                logger.info(f"Processing merge action for group {action['group_index']}")
                logger.info(f"  Labels: {action['labels']}")
                logger.info(f"  All nodes: {action['all_nodes']}")
                logger.info(f"  Reason: {action['reason']}")
                
                # Validate nodes exist and get their edge counts
                all_node_ids = action['all_nodes']
                nodes = validate_nodes_exist(session, all_node_ids)
                
                if len(nodes) != len(all_node_ids):
                    logger.warning(f"  ⚠️  Skipping: Some nodes not found in database")
                    failed_merges += 1
                    continue
                
                # Find the node with the most connections (highest edge count)
                node_edge_counts = {}
                for node_id, node in nodes.items():
                    edge_count = session.query(Edge).filter(
                        (Edge.source_id == node_id) | (Edge.target_id == node_id)
                    ).count()
                    node_edge_counts[node_id] = edge_count
                    logger.info(f"    Node {node_id} has {edge_count} edges")
                
                # Select target node (highest edge count) and source nodes
                target_node_id = max(node_edge_counts.keys(), key=lambda x: node_edge_counts[x])
                source_node_ids = [nid for nid in all_node_ids if nid != target_node_id]
                
                logger.info(f"  🎯 Target node: {target_node_id} (edge count: {node_edge_counts[target_node_id]})")
                logger.info(f"  📤 Source nodes: {source_node_ids}")
                
                if dry_run:
                    logger.info(f"  🔍 DRY RUN: Would merge {len(source_node_ids)} nodes into {target_node_id}")
                    successful_merges += 1
                    continue
                
                # Perform the merge
                target_node = nodes[target_node_id]
                source_nodes = [nodes[node_id] for node_id in source_node_ids]
                
                for source_node in source_nodes:
                    logger.info(f"  🔄 Merging {source_node.id} into {target_node.id}")
                    
                    # Use the existing merge function
                    # Note: merge_nodes(target_node_id, source_node_id, session) - target first, then source
                    merge_result = merge_nodes(
                        str(target_node.id),  # n1_id (target - the one we keep)
                        str(source_node.id),  # n2_id (source - the one we merge away)
                        session
                    )
                    
                    if merge_result:
                        logger.info(f"  ✅ Successfully merged {source_node.id} into {target_node.id}")
                        # Commit the merge to the database
                        session.commit()
                        logger.info(f"  💾 Changes committed to database")
                    else:
                        logger.error(f"  ❌ Failed to merge {source_node.id} into {target_node.id}")
                        failed_merges += 1
                        continue
                
                successful_merges += 1
                
            except Exception as e:
                logger.error(f"  ❌ Error processing merge action: {e}")
                failed_merges += 1
                session.rollback()
        
        # Summary
        logger.info(f"Auto-merge completed: {successful_merges} successful, {failed_merges} failed")
        
        if dry_run:
            logger.info("🔍 This was a dry run - no actual merges were performed")
            logger.info("Run with dry_run=False to perform actual merges")
        
        return {
            'successful_merges': successful_merges,
            'failed_merges': failed_merges,
            'total_actions': len(merge_actions)
        }
        
    except Exception as e:
        logger.error(f"Auto-merge failed: {e}")
        session.rollback()
        raise e
    finally:
        session.close()


def print_merge_preview():
    """Print a preview of what would be merged"""
    try:
        results = auto_merge_duplicates(dry_run=True)
        if results:
            print(f"\n🔍 MERGE PREVIEW")
            print(f"=" * 50)
            print(f"Total merge actions: {results['total_actions']}")
            print(f"Would merge: {results['successful_merges']}")
            print(f"Would fail: {results['failed_merges']}")
            print(f"\nRun with dry_run=False to perform actual merges")
    except Exception as e:
        print(f"❌ Preview failed: {e}")


if __name__ == "__main__":
    print("🔄 Auto-Merge Duplicates")
    print("=" * 50)
    
    try:
        # First, show preview
        print("🔍 Running preview first...")
        results = auto_merge_duplicates(dry_run=True)
        
        if results and results['total_actions'] > 0:
            print(f"\n" + "=" * 60)
            print("🚀 Ready to execute merges!")
            print(f"Total actions: {results['total_actions']}")
            print(f"Would merge: {results['successful_merges']}")
            print(f"Would fail: {results['failed_merges']}")
            
            # Ask user if they want to proceed
            response = input("\n❓ Do you want to execute these merges? (y/N): ").strip().lower()
            
            if response in ['y', 'yes']:
                print("\n🚀 Executing merges...")
                results = auto_merge_duplicates(dry_run=False)
                if results:
                    print(f"\n✅ Auto-merge completed!")
                    print(f"  Successful merges: {results['successful_merges']}")
                    print(f"  Failed merges: {results['failed_merges']}")
            else:
                print("🔍 Merges cancelled - only preview was shown")
        else:
            print("ℹ️  No merge actions found or all actions would fail")
            
    except Exception as e:
        print(f"❌ Auto-merge failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🏁 Auto-merge script finished")
