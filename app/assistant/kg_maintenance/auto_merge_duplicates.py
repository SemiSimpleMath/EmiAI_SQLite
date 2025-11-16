#!/usr/bin/env python3
"""
Auto-merge Duplicates Pipeline
Uses the sophisticated merging logic from kg_pipeline to merge duplicates found by duplicate_analysis_pipeline
"""

import json
import time
import glob
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
# Note: merge_nodes import removed - now using unified merge function from knowledge_graph_utils

from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def load_duplicate_analysis_report() -> List[Dict]:
    """
    Load the most recent duplicate analysis report
    """
    # Find the most recent analysis report (try both formats)
    # Look in dedupe_logs subfolder first, then current directory
    import os
    dedupe_logs_dir = "dedupe_logs"
    
    # Check dedupe_logs subfolder first
    if os.path.exists(dedupe_logs_dir):
        analysis_reports = glob.glob(os.path.join(dedupe_logs_dir, "duplicate_analysis_report_*.json"))
        node_reports = glob.glob(os.path.join(dedupe_logs_dir, "duplicate_nodes_report_*.json"))
    else:
        analysis_reports = []
        node_reports = []
    
    # Fallback to current directory if no reports found in dedupe_logs
    if not analysis_reports and not node_reports:
        analysis_reports = glob.glob("duplicate_analysis_report_*.json")
        node_reports = glob.glob("duplicate_nodes_report_*.json")
    
    all_reports = analysis_reports + node_reports
    if not all_reports:
        raise FileNotFoundError("No duplicate analysis report found. Run duplicate_analysis_pipeline or node_deduplication_pipeline first.")
    
    all_reports.sort(reverse=True)
    filename = all_reports[0]
    logger.info(f"Using most recent analysis report: {filename}")
    
    with open(filename, 'r') as f:
        report = json.load(f)
    
    # Handle different report formats
    if 'analysis_results' in report:
        # Format from duplicate_analysis_pipeline.py
        return report.get('analysis_results', [])
    elif 'duplicate_groups' in report:
        # Format from node_deduplication_pipeline.py - convert to expected format
        duplicate_groups = report.get('duplicate_groups', [])
        if duplicate_groups:
            # Convert simple node ID groups to the expected format
            converted_results = []
            for group_idx, node_ids in enumerate(duplicate_groups):
                if len(node_ids) >= 2:  # Only process groups with 2+ nodes
                    converted_results.append({
                        'group_id': f"group_{group_idx + 1}",
                        'nodes': node_ids,
                        'analysis_result': {
                            'merge_actions': [{
                                'merge': node_ids,
                                'labels': [f"node_{i}" for i in range(len(node_ids))],  # Placeholder labels
                                'reason': 'Duplicate nodes found by node deduplication pipeline'
                            }]
                        }
                    })
            return converted_results
        else:
            logger.warning("No duplicate groups found in node deduplication report")
            return []
    else:
        logger.warning(f"Unknown report format in {filename}")
        return []


def merge_duplicate_group(node_ids: List[str], session: Session, kg_utils: KnowledgeGraphUtils) -> Dict:
    """
    Merge a group of duplicate nodes using the unified intelligent merge function.
    This now uses the same sophisticated logic as the KG pipeline.
    
    Args:
        node_ids: List of node IDs to merge
        session: Database session
        kg_utils: KnowledgeGraphUtils instance
        
    Returns:
        Dictionary with merge results
    """
    if len(node_ids) < 2:
        return {"status": "skipped", "reason": "Need at least 2 nodes to merge"}
    
    try:
        # Get the node_data_merger agent
        node_data_merger = DI.agent_factory.create_agent("knowledge_graph_add::node_data_merger")
        
        # Use the unified merge function from KnowledgeGraphUtils
        result = kg_utils.merge_multiple_duplicates(node_ids, node_data_merger)
        
        if result["status"] == "completed":
            logger.info(f"✅ Successfully merged {result['total_merged']} nodes into {result['target_node_label']}")
        else:
            logger.error(f"❌ Merge failed: {result.get('error', 'Unknown error')}")
        
        return result
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Failed to merge group: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "node_ids": node_ids
        }


def run_auto_merge_pipeline(confidence_threshold: float = 0.8, max_groups: int = None, interactive: bool = True):
    """
    Run the auto-merge pipeline to merge duplicates found by the analysis pipeline
    
    Args:
        confidence_threshold: Minimum confidence to auto-merge (not used in current implementation)
        max_groups: Maximum number of groups to process
        interactive: If True, ask for approval before each merge
    """
    session = get_session()
    kg_utils = KnowledgeGraphUtils(session)
    
    try:
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        logger.info(f"🔍 Connecting to database: {db_uri}")
        
        # Load duplicate analysis results
        logger.info("📋 Loading duplicate analysis results...")
        analysis_results = load_duplicate_analysis_report()
        logger.info(f"📊 Found {len(analysis_results)} analysis results")
        
        if not analysis_results:
            logger.info("✅ No duplicate analysis results found!")
            return
        
        # Filter for groups with merge actions
        groups_with_merges = []
        for result in analysis_results:
            merge_actions = result.get('analysis_result', {}).get('merge_actions', [])
            if merge_actions:
                groups_with_merges.append(result)
        
        logger.info(f"🔗 Found {len(groups_with_merges)} groups with merge actions")
        
        if max_groups:
            groups_with_merges = groups_with_merges[:max_groups]
            logger.info(f"📝 Processing first {max_groups} groups")
        
        # Process each group
        merge_results = []
        processed_count = 0
        error_count = 0
        
        for group_idx, group_result in enumerate(groups_with_merges, 1):
            try:
                logger.info(f"🔄 Processing merge group {group_idx}/{len(groups_with_merges)}")
                
                merge_actions = group_result.get('analysis_result', {}).get('merge_actions', [])
                group_nodes = group_result.get('nodes', [])
                
                logger.info(f"   📝 Group nodes: {group_nodes}")
                logger.info(f"   🔗 Merge actions: {len(merge_actions)}")
                
                # Process each merge action in the group
                for action_idx, action in enumerate(merge_actions):
                    merge_ids = action.get('merge', [])
                    labels = action.get('labels', [])
                    reason = action.get('reason', 'No reason provided')
                    
                    logger.info(f"   🎯 Merge action {action_idx + 1}: {len(merge_ids)} nodes - {reason}")
                    logger.info(f"      Labels: {labels}")
                    logger.info(f"      Node IDs: {merge_ids}")
                    
                    # Show detailed information about what will be merged
                    if interactive:
                        print(f"\n{'='*80}")
                        print(f"🔍 MERGE PREVIEW - Group {group_idx}, Action {action_idx + 1}")
                        print(f"{'='*80}")
                        print(f"📝 Reason: {reason}")
                        print(f"🏷️  Labels: {labels}")
                        print(f"🔗 Nodes to merge: {len(merge_ids)}")
                        print()
                        
                        # Get detailed node information
                        for i, node_id in enumerate(merge_ids):
                            node = kg_utils.get_node_by_id(node_id)
                            if node:
                                # Get merge context which includes edge information
                                context = kg_utils.get_node_merge_context(node, edge_limit=5)
                                edge_count = len(context.get('edges_sample', [])) if context else 0
                                
                                print(f"   {i+1}. {node.label}")
                                print(f"      ID: {node_id}")
                                print(f"      Type: {node.node_type}")
                                print(f"      Edges: {edge_count}")
                                print(f"      Aliases: {node.aliases or []}")
                                print(f"      Created: {node.created_at}")
                                if context and context.get('edges_sample'):
                                    print(f"      Sample edges:")
                                    for edge in context['edges_sample'][:3]:  # Show first 3 edges
                                        direction = edge['direction']
                                        rel_type = edge['relationship_type']
                                        other_node = edge['related_node_label']
                                        print(f"        {direction}: {rel_type} -> {other_node}")
                                print()
                        
                        # Ask for approval
                        while True:
                            response = input("🤔 Do you want to proceed with this merge? (y/n/s=skip group/q=quit): ").lower().strip()
                            if response in ['y', 'yes']:
                                print("✅ Proceeding with merge...")
                                break
                            elif response in ['n', 'no']:
                                print("❌ Skipping this merge action")
                                merge_result = {
                                    "status": "skipped",
                                    "reason": "User declined",
                                    "group_index": group_idx,
                                    "action_index": action_idx,
                                    "reason": reason,
                                    "labels": labels
                                }
                                merge_results.append(merge_result)
                                continue
                            elif response in ['s', 'skip']:
                                print("⏭️  Skipping entire group")
                                break
                            elif response in ['q', 'quit']:
                                print("🛑 Exiting pipeline")
                                return
                            else:
                                print("Please enter 'y' (yes), 'n' (no), 's' (skip group), or 'q' (quit)")
                        
                        if response in ['s', 'skip']:
                            break
                    
                    # Perform the merge
                    merge_result = merge_duplicate_group(merge_ids, session, kg_utils)
                    merge_result.update({
                        "group_index": group_idx,
                        "action_index": action_idx,
                        "reason": reason,
                        "labels": labels
                    })
                    
                    merge_results.append(merge_result)
                    
                    if merge_result["status"] == "completed":
                        processed_count += 1
                        logger.info(f"   ✅ Merge completed successfully")
                    else:
                        error_count += 1
                        logger.error(f"   ❌ Merge failed: {merge_result.get('error', 'Unknown error')}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"   ❌ Error processing group {group_idx}: {e}")
                session.rollback()
        
        # Generate summary report
        logger.info(f"\n{'='*60}")
        logger.info(f"🎉 AUTO-MERGE PIPELINE COMPLETED")
        logger.info(f"{'='*60}")
        logger.info(f"📊 Groups processed: {len(groups_with_merges)}")
        logger.info(f"✅ Successful merges: {processed_count}")
        logger.info(f"❌ Failed merges: {error_count}")
        
        # Save detailed results
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        results_file = f"auto_merge_results_{timestamp}.json"
        
        # Ensure dedupe_logs directory exists
        import os
        os.makedirs('dedupe_logs', exist_ok=True)
        
        # Save to dedupe_logs subfolder
        filepath = os.path.join('dedupe_logs', results_file)
        with open(filepath, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "summary": {
                    "groups_processed": len(groups_with_merges),
                    "successful_merges": processed_count,
                    "failed_merges": error_count
                },
                "merge_results": merge_results
            }, f, indent=2, default=str)
        
        logger.info(f"📄 Detailed results saved to: {filepath}")
        
    except Exception as e:
        logger.error(f"❌ Auto-merge pipeline failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import app.assistant.tests.test_setup
    
    # Run the auto-merge pipeline with interactive approval
    run_auto_merge_pipeline(max_groups=10, interactive=True)  # Start with 10 groups for testing
