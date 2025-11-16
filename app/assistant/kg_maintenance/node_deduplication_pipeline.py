"""
Node Deduplication Pipeline
Identifies potential duplicate nodes that should be merged
"""

import json
import time
from typing import List, Dict, Tuple, Set
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.base import get_session, Base
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_core.kg_tools import inspect_node_neighborhood
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

# Import the new tracking system
from app.models.node_analysis_tracking import (
    get_node_analysis_status,
    mark_node_as_analyzed,
    get_nodes_needing_analysis,
    get_analysis_statistics
)

logger = get_logger(__name__)


def find_exact_label_duplicates(session: Session) -> List[List[Node]]:
    """
    Find nodes with exactly the same label
    Returns list of groups, each group contains duplicate nodes
    """
    duplicates = []
    
    # Find nodes with same label
    label_counts = session.query(
        Node.label, 
        func.count(Node.id)
    ).filter(
        Node.label.isnot(None)
    ).group_by(Node.label).having(
        func.count(Node.id) > 1
    ).all()
    
    for label, count in label_counts:
        if count > 1:
            nodes = session.query(Node).filter(Node.label == label).all()
            duplicates.append(nodes)
            logger.info(f"Found {count} nodes with label '{label}'")
    
    return duplicates


def find_similar_label_duplicates(session: Session, similarity_threshold: float = 0.8) -> List[List[Node]]:
    """
    Find nodes with similar labels using fuzzy matching
    Returns list of groups, each group contains potentially duplicate nodes
    """
    from difflib import SequenceMatcher
    
    duplicates = []
    all_nodes = session.query(Node).filter(Node.label.isnot(None)).all()
    processed = set()
    
    for i, node1 in enumerate(all_nodes):
        if str(node1.id) in processed:
            continue
            
        similar_group = [node1]
        processed.add(str(node1.id))
        
        for node2 in all_nodes[i+1:]:
            if str(node2.id) in processed:
                continue
                
            # Calculate similarity
            similarity = SequenceMatcher(None, node1.label.lower(), node2.label.lower()).ratio()
            
            if similarity >= similarity_threshold:
                similar_group.append(node2)
                processed.add(str(node2.id))
                logger.info(f"Similar labels: '{node1.label}' ~ '{node2.label}' (similarity: {similarity:.2f})")
        
        if len(similar_group) > 1:
            duplicates.append(similar_group)
    
    return duplicates


def find_semantic_duplicates(session: Session, similarity_threshold: float = 0.8) -> List[List[Node]]:
    """
    Find semantically similar nodes using embeddings
    Returns list of groups, each group contains semantically similar nodes
    """
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
    except ImportError:
        logger.warning("scikit-learn not available, skipping semantic duplicate detection")
        return []
    
    duplicates = []
    
    # Get all nodes with descriptions or context
    nodes_with_context = []
    for node in session.query(Node).all():
        context = ""
        if node.description:
            context = node.description
        elif node.attributes and 'description' in node.attributes:
            context = node.attributes['description']
        
        if context and len(context) > 10:  # Only consider nodes with meaningful context
            nodes_with_context.append((node, context))
    
    if len(nodes_with_context) < 2:
        return []
    
    # Create embeddings (this would need to be implemented based on your embedding system)
    # For now, we'll use a simple approach
    logger.info(f"Analyzing {len(nodes_with_context)} nodes with context for semantic similarity")
    
    # Group by node type first to reduce false positives
    by_type = defaultdict(list)
    for node, context in nodes_with_context:
        by_type[node.node_type].append((node, context))
    
    for node_type, type_nodes in by_type.items():
        if len(type_nodes) < 2:
            continue
            
        # Simple similarity based on word overlap (placeholder for proper embeddings)
        for i, (node1, context1) in enumerate(type_nodes):
            similar_group = [node1]
            
            for node2, context2 in type_nodes[i+1:]:
                # Simple word overlap similarity
                words1 = set(context1.lower().split())
                words2 = set(context2.lower().split())
                
                if len(words1) > 0 and len(words2) > 0:
                    overlap = len(words1.intersection(words2))
                    total = len(words1.union(words2))
                    similarity = overlap / total if total > 0 else 0
                    
                    if similarity >= similarity_threshold:
                        similar_group.append(node2)
                        logger.info(f"Semantic similarity: '{node1.label}' ~ '{node2.label}' (similarity: {similarity:.2f})")
            
            if len(similar_group) > 1:
                duplicates.append(similar_group)
    
    return duplicates


def find_structural_duplicates(session: Session) -> List[List[Node]]:
    """
    Find nodes with similar structural patterns (similar edge types and connections)
    Returns list of groups, each group contains structurally similar nodes
    """
    duplicates = []
    
    # Get all nodes and their edge patterns
    node_patterns = {}
    
    for node in session.query(Node).all():
        # Get incoming and outgoing edges
        incoming = session.query(Edge).filter(Edge.target_id == node.id).all()
        outgoing = session.query(Edge).filter(Edge.source_id == node.id).all()
        
        # Create pattern signature
        pattern = {
            'incoming_types': sorted([e.relationship_type for e in incoming]),
            'outgoing_types': sorted([e.relationship_type for e in outgoing]),
            'total_edges': len(incoming) + len(outgoing)
        }
        
        pattern_key = str(pattern)
        if pattern_key not in node_patterns:
            node_patterns[pattern_key] = []
        node_patterns[pattern_key].append(node)
    
    # Find patterns with multiple nodes
    for pattern_key, nodes in node_patterns.items():
        if len(nodes) > 1:
            duplicates.append(nodes)
            logger.info(f"Found {len(nodes)} nodes with similar structural pattern")
    
    return duplicates


def analyze_duplicate_group(nodes: List[Node], session: Session) -> Dict:
    """
    Analyze a group of potentially duplicate nodes
    Returns analysis result with confidence and suggested action
    """
    if len(nodes) < 2:
        return {"is_duplicate": False, "confidence": 0.0}
    
    # Get detailed information about each node
    node_details = []
    for node in nodes:
        details = {
            'id': str(node.id),
            'label': node.label,
            'type': node.node_type,
            'category': node.category or 'entity',
            'semantic_label': node.semantic_label,
            'edge_count': session.query(Edge).filter(
                or_(Edge.source_id == node.id, Edge.target_id == node.id)
            ).count(),
            'attributes': node.attributes or {},
            'created_at': node.created_at,
            'updated_at': node.updated_at
        }
        node_details.append(details)
    
    # Calculate similarity scores
    label_similarity = 1.0 if all(n['label'] == node_details[0]['label'] for n in node_details) else 0.0
    
    # Type consistency
    type_consistency = 1.0 if all(n['type'] == node_details[0]['type'] for n in node_details) else 0.0
    
    # Category consistency
    category_consistency = 1.0 if all(n['category'] == node_details[0]['category'] for n in node_details) else 0.0
    
    # Semantic type consistency
    semantic_label_consistency = 1.0 if all(n['semantic_label'] == node_details[0]['semantic_label'] for n in node_details) else 0.0
    
    # Edge count similarity (closer counts = higher similarity)
    edge_counts = [n['edge_count'] for n in node_details]
    edge_similarity = 1.0 - (max(edge_counts) - min(edge_counts)) / max(max(edge_counts), 1)
    
    # Overall confidence
    confidence = (label_similarity * 0.4 + type_consistency * 0.25 + 
                 category_consistency * 0.15 + semantic_label_consistency * 0.1 + edge_similarity * 0.1)
    
    # Determine if this is likely a duplicate
    is_duplicate = confidence > 0.7
    
    # Suggest action
    if is_duplicate:
        if label_similarity > 0.9 and type_consistency > 0.9:
            suggested_action = "merge_high_confidence"
        elif confidence > 0.8:
            suggested_action = "merge_medium_confidence"
        else:
            suggested_action = "review_manually"
    else:
        suggested_action = "keep_separate"
    
    return {
        "is_duplicate": is_duplicate,
        "confidence": confidence,
        "suggested_action": suggested_action,
        "similarity_breakdown": {
            "label_similarity": label_similarity,
            "type_consistency": type_consistency,
            "category_consistency": category_consistency,
            "semantic_label_consistency": semantic_label_consistency,
            "edge_similarity": edge_similarity
        },
        "node_details": node_details
    }


def ensure_node_analysis_tracking_table_exists(session):
    """Ensure the node_analysis_tracking table exists in the database"""
    try:
        engine = session.bind
        logger.info(f"🔧 Ensuring node_analysis_tracking table exists on engine: {engine.url}")
        
        from app.models.node_analysis_tracking import NodeAnalysisTracking
        from app.models.base import Base
        
        # Use checkfirst=True to idempotently create the table and its indexes
        Base.metadata.create_all(engine, checkfirst=True)
        
        logger.info("✅ node_analysis_tracking table ensured")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to ensure node_analysis_tracking table: {e}")
        raise e


def run_node_deduplication_pipeline(skip_analyzed: bool = True, force_reanalyze: bool = False, 
                                  max_groups: int = None, similarity_threshold: float = 0.8):
    """
    Main pipeline function to identify duplicate nodes
    
    Args:
        skip_analyzed: If True, skip duplicate groups that have already been analyzed
        force_reanalyze: If True, reanalyze all duplicate groups regardless of previous analysis
        max_groups: Maximum number of duplicate groups to process (None for all)
        similarity_threshold: Threshold for semantic similarity detection
    """
    session = get_session()
    
    try:
        # Ensure the tracking table exists before we try to use it
        ensure_node_analysis_tracking_table_exists(session)
        
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        logger.info(f"🔍 Connecting to database: {db_uri}")
        
        # Now that the table exists, we can get analysis statistics
        stats = get_analysis_statistics(session)
        logger.info(f"📊 Current analysis coverage: {stats['analyzed_nodes']}/{stats['total_nodes']} nodes ({stats['coverage_percentage']:.1f}%)")
        
        # Find duplicate candidates using different strategies
        logger.info("🔍 Searching for duplicate nodes...")
        
        all_duplicate_groups = []
        
        # 1. Exact label duplicates
        logger.info("1. Finding exact label duplicates...")
        exact_duplicates = find_exact_label_duplicates(session)
        all_duplicate_groups.extend(exact_duplicates)
        logger.info(f"   Found {len(exact_duplicates)} exact label duplicate groups")
        
        # 2. Similar label duplicates
        logger.info("2. Finding similar label duplicates...")
        similar_duplicates = find_similar_label_duplicates(session, similarity_threshold)
        all_duplicate_groups.extend(similar_duplicates)
        logger.info(f"   Found {len(similar_duplicates)} similar label duplicate groups")
        
        # 3. Semantic duplicates
        logger.info("3. Finding semantic duplicates...")
        semantic_duplicates = find_semantic_duplicates(session, similarity_threshold)
        all_duplicate_groups.extend(semantic_duplicates)
        logger.info(f"   Found {len(semantic_duplicates)} semantic duplicate groups")
        
        # 4. Structural duplicates
        logger.info("4. Finding structural duplicates...")
        structural_duplicates = find_structural_duplicates(session)
        all_duplicate_groups.extend(structural_duplicates)
        logger.info(f"   Found {len(structural_duplicates)} structural duplicate groups")
        
        # Remove duplicate groups (same nodes in different detection methods)
        unique_groups = []
        seen_nodes = set()
        
        for group in all_duplicate_groups:
            group_key = tuple(sorted(str(n.id) for n in group))
            if group_key not in seen_nodes:
                unique_groups.append(group)
                seen_nodes.add(group_key)
        
        logger.info(f"📊 Total unique duplicate groups found: {len(unique_groups)}")
        
        # Limit groups if specified
        if max_groups and len(unique_groups) > max_groups:
            unique_groups = unique_groups[:max_groups]
            logger.info(f"📊 Limited to {max_groups} groups for processing")
        
        # Analyze each duplicate group
        duplicate_results = []
        processed_count = 0
        error_count = 0
        
        for group_idx, duplicate_group in enumerate(unique_groups):
            logger.info(f"Processing duplicate group {group_idx + 1}/{len(unique_groups)}")
            logger.info(f"   Nodes: {[n.label for n in duplicate_group]}")
            
            try:
                # Analyze the duplicate group
                analysis_result = analyze_duplicate_group(duplicate_group, session)
                
                if analysis_result["is_duplicate"]:
                    # Create result for each node in the group
                    group_id = f"group_{group_idx + 1}"
                    for node in duplicate_group:
                        duplicate_info = {
                            'node_id': str(node.id),
                            'label': node.label,
                            'type': node.node_type,
                            'category': node.category or 'entity',
                            'semantic_label': node.semantic_label,
                            'duplicate_group_id': group_id,
                            'duplicate_group_size': len(duplicate_group),
                            'duplicate_confidence': analysis_result['confidence'],
                            'suggested_action': analysis_result['suggested_action'],
                            'similarity_breakdown': analysis_result['similarity_breakdown'],
                            'other_nodes_in_group': [
                                {'id': str(n.id), 'label': n.label, 'type': n.node_type}
                                for n in duplicate_group if n.id != node.id
                            ]
                        }
                        duplicate_results.append(duplicate_info)
                    
                    logger.info(f"   ✅ Confirmed as duplicate (confidence: {analysis_result['confidence']:.2f})")
                else:
                    logger.info(f"   ❌ Not a duplicate (confidence: {analysis_result['confidence']:.2f})")
                
                processed_count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing duplicate group {group_idx + 1}: {e}")
                session.rollback()
        
        logger.info(f"Pipeline completed: {processed_count} groups processed, {len(duplicate_results)} duplicate nodes found, {error_count} errors")
        
        # Sort results by confidence
        duplicate_results.sort(key=lambda x: x['duplicate_confidence'], reverse=True)
        
        # Also create simple format for compatibility with analysis pipeline
        duplicate_groups = []
        for group in unique_groups:
            if len(group) >= 2:
                duplicate_groups.append([str(node.id) for node in group])
        
        return {
            "processed_groups": processed_count,
            "duplicate_nodes_found": len(duplicate_results),
            "errors": error_count,
            "duplicate_results": duplicate_results,
            "total_groups_analyzed": len(unique_groups),
            "duplicate_groups": duplicate_groups  # Simple format for analysis pipeline
        }
        
    finally:
        session.close()


def save_duplicate_report(duplicate_results: List[Dict], filename: str = None):
    """
    Save the duplicate nodes report to a JSON file
    """
    if filename is None:
        from datetime import datetime
        filename = f"duplicate_nodes_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Extract duplicate groups from results if available
    duplicate_groups = []
    if duplicate_results:
        # Group by duplicate_group_id
        groups_by_id = {}
        for result in duplicate_results:
            group_id = result.get('duplicate_group_id')
            if group_id:
                if group_id not in groups_by_id:
                    groups_by_id[group_id] = []
                groups_by_id[group_id].append(result['node_id'])
        
        # Convert to simple format
        for group in groups_by_id.values():
            if len(group) >= 2:
                duplicate_groups.append(group)
    
    report = {
        "timestamp": str(datetime.now()),
        "total_duplicate_nodes": len(duplicate_results),
        "duplicate_results": duplicate_results,
        "duplicate_groups": duplicate_groups  # Simple format for analysis pipeline
    }
    
    # Ensure dedupe_logs directory exists
    import os
    os.makedirs('dedupe_logs', exist_ok=True)
    
    # Save to dedupe_logs subfolder
    filepath = os.path.join('dedupe_logs', filename)
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Duplicate nodes report saved to {filepath}")
    return filename


def print_duplicate_summary(duplicate_results: List[Dict]):
    """
    Print a summary of duplicate nodes
    """
    print(f"\n🔍 DUPLICATE NODES SUMMARY")
    print(f"=" * 50)
    print(f"Total duplicate nodes: {len(duplicate_results)}")
    
    if not duplicate_results:
        print("No duplicate nodes found! 🎉")
        return
    
    # Group by suggested action
    by_action = defaultdict(list)
    for node in duplicate_results:
        by_action[node['suggested_action']].append(node)
    
    # Show high confidence merges first
    if by_action.get('merge_high_confidence'):
        nodes = by_action['merge_high_confidence']
        print(f"\n🚀 HIGH CONFIDENCE MERGES ({len(nodes)} nodes):")
        for node in nodes[:10]:  # Show first 10
            print(f"  • {node['label']} ({node['type']}) - Confidence: {node['duplicate_confidence']:.2f}")
            print(f"    Group size: {node['duplicate_group_size']} nodes")
            if len(nodes) > 10:
                print(f"    ... and {len(nodes) - 10} more")
    
    if by_action.get('merge_medium_confidence'):
        nodes = by_action['merge_medium_confidence']
        print(f"\n⚠️ MEDIUM CONFIDENCE MERGES ({len(nodes)} nodes):")
        for node in nodes[:10]:
            print(f"  • {node['label']} ({node['type']}) - Confidence: {node['duplicate_confidence']:.2f}")
            if len(nodes) > 10:
                print(f"    ... and {len(nodes) - 10} more")
    
    if by_action.get('review_manually'):
        nodes = by_action['review_manually']
        print(f"\n🔍 MANUAL REVIEW NEEDED ({len(nodes)} nodes):")
        for node in nodes[:10]:
            print(f"  • {node['label']} ({node['type']}) - Confidence: {node['duplicate_confidence']:.2f}")
            if len(nodes) > 10:
                print(f"    ... and {len(nodes) - 10} more")
    
    # Show some statistics
    confidences = [n['duplicate_confidence'] for n in duplicate_results]
    group_sizes = [n['duplicate_group_size'] for n in duplicate_results]
    
    print(f"\n📊 STATISTICS:")
    print(f"  Average confidence: {sum(confidences)/len(confidences):.2f}")
    print(f"  Average group size: {sum(group_sizes)/len(group_sizes):.1f}")
    print(f"  High confidence (≥0.9): {sum(1 for c in confidences if c >= 0.9)}")
    print(f"  Medium confidence (0.7-0.9): {sum(1 for c in confidences if 0.7 <= c < 0.9)}")
    print(f"  Low confidence (<0.7): {sum(1 for c in confidences if c < 0.7)}")


if __name__ == "__main__":
    from datetime import datetime
    
    print("🔍 Running Node Deduplication Pipeline...")
    print("=" * 50)
    
    # Show current analysis coverage
    session = get_session()
    try:
        # Debug: Confirm which database we're using
        from app.models.base import get_database_uri
        db_uri = get_database_uri()
        print(f"🔍 Connecting to database: {db_uri}")
        
        # Initialize the tracking table using the simplified approach
        print("🔧 Ensuring node analysis tracking table exists...")
        engine = session.bind
        
        # Use the simple approach like knowledge_graph_db.py
        from app.models.node_analysis_tracking import initialize_node_analysis_tracking_db
        initialize_node_analysis_tracking_db()
        print("   ✅ Table initialization completed")
        
        stats = get_analysis_statistics(session)
        print(f"📊 Current coverage: {stats['analyzed_nodes']}/{stats['total_nodes']} nodes ({stats['coverage_percentage']:.1f}%)")
    finally:
        session.close()
    
    print("\n🔧 Choose processing mode:")
    print("   1. Process all duplicate groups (default)")
    print("   2. Process limited number of groups")
    print("   3. Custom similarity threshold")
    
    # For now, default to processing all duplicate groups
    try:
        print("\n🚀 Processing all duplicate groups...")
        result = run_node_deduplication_pipeline(
            skip_analyzed=True, 
            force_reanalyze=False,
            max_groups=None,
            similarity_threshold=0.8
        )
        
        # Print summary
        print_duplicate_summary(result['duplicate_results'])
        
        # Save report
        filename = save_duplicate_report(result['duplicate_results'])
        print(f"\n📄 Detailed report saved to: {filename}")
        
        print(f"\n✅ Pipeline completed!")
        print(f"  Groups processed: {result['processed_groups']}")
        print(f"  Duplicate nodes found: {result['duplicate_nodes_found']}")
        print(f"  Errors: {result['errors']}")
        print(f"  Total groups analyzed: {result['total_groups_analyzed']}")
        
    except Exception as e:
        print(f"❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("🏁 Node Deduplication Pipeline execution finished")
