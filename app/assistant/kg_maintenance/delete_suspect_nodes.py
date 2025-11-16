"""
Delete Suspect Nodes Utility
Safely deletes nodes identified by the cleanup pipeline along with their edges
"""

import json
from typing import List, Dict
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def load_suspect_report(filename: str) -> Dict:
    """
    Load the suspect nodes report from JSON file
    """
    try:
        with open(filename, 'r') as f:
            report = json.load(f)
        logger.info(f"Loaded suspect report: {report['total_suspect_nodes']} nodes")
        return report
    except FileNotFoundError:
        logger.error(f"Report file not found: {filename}")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in report file: {filename}")
        sys.exit(1)


def delete_node_and_edges(session: Session, node_id: str, node_label: str) -> Dict:
    """
    Delete a node and all its incoming/outgoing edges
    Returns statistics about what was deleted
    """
    try:
        # Find the node
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            return {
                'success': False,
                'error': f'Node {node_id} not found',
                'edges_deleted': 0
            }
        
        # Count edges before deletion
        incoming_edges = session.query(Edge).filter(Edge.target_id == node_id).all()
        outgoing_edges = session.query(Edge).filter(Edge.source_id == node_id).all()
        total_edges = len(incoming_edges) + len(outgoing_edges)
        
        # Delete incoming edges
        for edge in incoming_edges:
            session.delete(edge)
        
        # Delete outgoing edges
        for edge in outgoing_edges:
            session.delete(edge)
        
        # Delete the node itself
        session.delete(node)
        
        # Commit the transaction
        session.commit()
        
        logger.info(f"Deleted node '{node_label}' ({node_id}) and {total_edges} edges")
        
        return {
            'success': True,
            'node_label': node_label,
            'node_id': node_id,
            'incoming_edges_deleted': len(incoming_edges),
            'outgoing_edges_deleted': len(outgoing_edges),
            'total_edges_deleted': total_edges
        }
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting node {node_label} ({node_id}): {e}")
        return {
            'success': False,
            'error': str(e),
            'node_label': node_label,
            'node_id': node_id,
            'edges_deleted': 0
        }


def delete_suspect_nodes(report_filename: str, dry_run: bool = True, priority_filter: str = None, cleanup_orphans: bool = True, debug_mode: bool = False):
    """
    Delete suspect nodes from the report and optionally clean up orphaned nodes
    
    Args:
        report_filename: Path to the suspect nodes JSON report
        dry_run: If True, only show what would be deleted (default: True for safety)
        priority_filter: Only delete nodes with this priority ('high', 'medium', 'low', None for all)
        cleanup_orphans: Whether to clean up orphaned nodes after deletion
        debug_mode: If True, only delete the first node (for testing)
    """
    # Load the report
    report = load_suspect_report(report_filename)
    suspect_nodes = report['suspect_nodes']
    
    # Filter by priority if specified
    if priority_filter:
        suspect_nodes = [node for node in suspect_nodes if node['cleanup_priority'] == priority_filter]
        logger.info(f"Filtered to {len(suspect_nodes)} nodes with priority '{priority_filter}'")
    
    if not suspect_nodes:
        logger.info("No nodes to delete!")
        return
    
    # Debug mode: only process the first node
    if debug_mode:
        suspect_nodes = suspect_nodes[:1]
        print(f"\n🔍 DEBUG MODE: Only processing the first node")
        print("=" * 50)
    
    # Group by priority for display
    by_priority = {}
    for node in suspect_nodes:
        priority = node['cleanup_priority']
        if priority not in by_priority:
            by_priority[priority] = []
        by_priority[priority].append(node)
    
    # Show what will be deleted
    mode_text = "DEBUG MODE" if debug_mode else ("DRY RUN" if dry_run else "ACTUAL DELETION")
    print(f"\n🗑️  NODES TO DELETE ({mode_text}):")
    print("=" * 60)
    
    for priority in ['high', 'medium', 'low']:
        if priority in by_priority:
            nodes = by_priority[priority]
            print(f"\n{priority.upper()} PRIORITY ({len(nodes)} nodes):")
            for node in nodes:
                print(f"  • {node['label']} ({node['type']}) - {node['edge_count']} edges")
                print(f"    Reason: {node['suspect_reason'][:80]}...")
    
    # Ask for confirmation if not dry run
    if not dry_run:
        if debug_mode:
            print(f"\n🔍 DEBUG MODE: This will delete ONLY the first node and its edges for testing!")
        else:
            print(f"\n⚠️  WARNING: This will permanently delete {len(suspect_nodes)} nodes and their edges!")
        if cleanup_orphans:
            print("⚠️  Orphaned nodes will also be cleaned up after deletion!")
        response = input("Are you sure you want to proceed? (type 'yes' to confirm): ")
        if response.lower() != 'yes':
            print("Deletion cancelled.")
            return
    
    # Perform deletion
    session = get_session()
    deletion_stats = {
        'total_nodes': len(suspect_nodes),
        'successful_deletions': 0,
        'failed_deletions': 0,
        'total_edges_deleted': 0,
        'errors': []
    }
    
    try:
        for i, node in enumerate(suspect_nodes, 1):
            print(f"\nProcessing {i}/{len(suspect_nodes)}: {node['label']}")
            
            if dry_run:
                print(f"  [DRY RUN] Would delete node '{node['label']}' and {node['edge_count']} edges")
                deletion_stats['successful_deletions'] += 1
                deletion_stats['total_edges_deleted'] += node['edge_count']
            else:
                result = delete_node_and_edges(session, node['node_id'], node['label'])
                
                if result['success']:
                    deletion_stats['successful_deletions'] += 1
                    deletion_stats['total_edges_deleted'] += result['total_edges_deleted']
                else:
                    deletion_stats['failed_deletions'] += 1
                    deletion_stats['errors'].append(result['error'])
        
        # Clean up orphaned nodes if requested
        if cleanup_orphans and not dry_run:
            print(f"\n🧹 Cleaning up orphaned nodes...")
            orphan_stats = cleanup_orphaned_nodes(session, dry_run=False)
            deletion_stats['orphan_cleanup'] = orphan_stats
        elif cleanup_orphans and dry_run:
            print(f"\n🧹 [DRY RUN] Would clean up orphaned nodes...")
            orphan_stats = cleanup_orphaned_nodes(session, dry_run=True)
            deletion_stats['orphan_cleanup'] = orphan_stats
    
    finally:
        session.close()
    
    # Print summary
    print(f"\n📊 DELETION SUMMARY:")
    print("=" * 40)
    print(f"Total nodes processed: {deletion_stats['total_nodes']}")
    print(f"Successful deletions: {deletion_stats['successful_deletions']}")
    print(f"Failed deletions: {deletion_stats['failed_deletions']}")
    print(f"Total edges deleted: {deletion_stats['total_edges_deleted']}")
    
    if 'orphan_cleanup' in deletion_stats:
        orphan_stats = deletion_stats['orphan_cleanup']
        print(f"Orphan cleanup: {orphan_stats['deleted']} orphaned nodes deleted")
    
    if deletion_stats['errors']:
        print(f"\n❌ ERRORS:")
        for error in deletion_stats['errors']:
            print(f"  • {error}")
    
    if dry_run:
        print(f"\n💡 To perform actual deletion, run with dry_run=False")
    elif debug_mode:
        print(f"\n🔍 DEBUG MODE COMPLETE: One node was deleted for testing")
        print(f"💡 To perform full deletion, run with debug_mode=False")


def create_backup_before_deletion(report_filename: str, backup_filename: str = None):
    """
    Create a backup of the suspect nodes before deletion
    """
    if backup_filename is None:
        from datetime import datetime
        backup_filename = f"backup_before_deletion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = load_suspect_report(report_filename)
    
    # Create backup with additional metadata
    backup = {
        "backup_timestamp": str(datetime.now()),
        "original_report": report,
        "backup_note": "Backup created before deletion of suspect nodes"
    }
    
    with open(backup_filename, 'w') as f:
        json.dump(backup, f, indent=2)
    
    logger.info(f"Backup created: {backup_filename}")
    return backup_filename


def find_orphaned_nodes(session: Session) -> List[Dict]:
    """
    Find nodes that have no incoming or outgoing edges (orphans)
    Returns list of orphaned node info
    """
    # Get all nodes
    all_nodes = session.query(Node).all()
    orphaned_nodes = []
    
    for node in all_nodes:
        # Skip Jukka (he should never be orphaned)
        if node.label == "Jukka":
            continue
            
        # Count edges
        incoming_count = session.query(Edge).filter(Edge.target_id == node.id).count()
        outgoing_count = session.query(Edge).filter(Edge.source_id == node.id).count()
        total_edges = incoming_count + outgoing_count
        
        if total_edges == 0:
            orphaned_nodes.append({
                'node_id': str(node.id),
                'label': node.label,
                'type': node.node_type,
                'attributes': node.attributes,
                'created_at': str(node.created_at) if node.created_at else None
            })
    
    return orphaned_nodes


def cleanup_orphaned_nodes(session: Session, dry_run: bool = True, exclude_types: List[str] = None) -> Dict:
    """
    Clean up orphaned nodes (nodes with no edges)
    
    Args:
        session: Database session
        dry_run: If True, only show what would be deleted
        exclude_types: Node types to exclude from cleanup (e.g., ['person', 'place'])
    
    Returns:
        Dictionary with cleanup statistics
    """
    if exclude_types is None:
        exclude_types = ['person']  # Generally don't delete orphaned people
    
    orphaned_nodes = find_orphaned_nodes(session)
    
    # Filter out excluded types
    filtered_orphans = []
    for node in orphaned_nodes:
        if node['type'] not in exclude_types:
            filtered_orphans.append(node)
        else:
            logger.info(f"Excluding orphaned {node['type']}: {node['label']}")
    
    if not filtered_orphans:
        logger.info("No orphaned nodes to clean up!")
        return {
            'total_orphans': len(orphaned_nodes),
            'filtered_orphans': 0,
            'deleted': 0,
            'errors': []
        }
    
    print(f"\n🧹 ORPHANED NODES CLEANUP ({'DRY RUN' if dry_run else 'ACTUAL DELETION'}):")
    print("=" * 50)
    print(f"Total orphaned nodes: {len(orphaned_nodes)}")
    print(f"Orphans to delete (excluding {exclude_types}): {len(filtered_orphans)}")
    
    if filtered_orphans:
        print(f"\nOrphaned nodes to delete:")
        for node in filtered_orphans:
            print(f"  • {node['label']} ({node['type']})")
    
    # Ask for confirmation if not dry run
    if not dry_run and filtered_orphans:
        print(f"\n⚠️  WARNING: This will permanently delete {len(filtered_orphans)} orphaned nodes!")
        response = input("Are you sure you want to proceed? (type 'yes' to confirm): ")
        if response.lower() != 'yes':
            print("Orphan cleanup cancelled.")
            return {
                'total_orphans': len(orphaned_nodes),
                'filtered_orphans': len(filtered_orphans),
                'deleted': 0,
                'errors': ['User cancelled']
            }
    
    # Perform deletion
    deleted_count = 0
    errors = []
    
    for node in filtered_orphans:
        try:
            if dry_run:
                print(f"  [DRY RUN] Would delete orphaned node: {node['label']}")
                deleted_count += 1
            else:
                # Find and delete the node
                db_node = session.query(Node).filter(Node.id == node['node_id']).first()
                if db_node:
                    session.delete(db_node)
                    session.commit()
                    logger.info(f"Deleted orphaned node: {node['label']}")
                    deleted_count += 1
                else:
                    errors.append(f"Node {node['label']} not found in database")
        except Exception as e:
            session.rollback()
            error_msg = f"Error deleting orphaned node {node['label']}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    print(f"\n📊 ORPHAN CLEANUP SUMMARY:")
    print(f"  Total orphaned nodes: {len(orphaned_nodes)}")
    print(f"  Orphans to delete: {len(filtered_orphans)}")
    print(f"  Successfully deleted: {deleted_count}")
    print(f"  Errors: {len(errors)}")
    
    if errors:
        print(f"\n❌ ERRORS:")
        for error in errors:
            print(f"  • {error}")
    
    return {
        'total_orphans': len(orphaned_nodes),
        'filtered_orphans': len(filtered_orphans),
        'deleted': deleted_count,
        'errors': errors
    }


if __name__ == "__main__":
    import argparse
    import sys
    from datetime import datetime
    
    # Check if running from IDE (no command line args)
    if len(sys.argv) == 1:
        print("🗑️  Suspect Node Deletion Utility (IDE Mode)")
        print("=" * 50)
        print("Running in dry-run mode (safe preview only)")
        print()
        
        # Use the existing suspect nodes report
        report_file = "suspect_nodes_report_20250817_220519.json"
        
        # Set default values for IDE mode
        dry_run = True
        priority_filter = None
        backup = False
        cleanup_orphans = True
        debug_mode = False
        
        print(f"\nUsing report file: {report_file}")
        print("Mode: DRY RUN (safe preview)")
        print()
        print("Options:")
        print("  1. Dry run (preview only) - default")
        print("  2. Debug mode (delete 1 node)")
        print("  3. Full deletion")
        
        choice = input("\nEnter choice (1-3, default=1): ").strip()
        if choice == "2":
            dry_run = False
            debug_mode = True
            print("🔍 DEBUG MODE: Will delete only the first node")
        elif choice == "3":
            dry_run = False
            debug_mode = False
            print("⚠️  FULL DELETION MODE: Will delete all suspect nodes")
        else:
            print("DRY RUN MODE: Preview only")
        print()
        
    else:
        # Command line mode
        parser = argparse.ArgumentParser(description="Delete suspect nodes from knowledge graph")
        parser.add_argument("report_file", help="Path to suspect nodes JSON report")
        parser.add_argument("--dry-run", action="store_true", default=True, 
                           help="Show what would be deleted without actually deleting (default: True)")
        parser.add_argument("--priority", choices=['high', 'medium', 'low'], 
                           help="Only delete nodes with this priority level")
        parser.add_argument("--backup", action="store_true", 
                           help="Create backup before deletion")
        parser.add_argument("--no-orphan-cleanup", action="store_true", 
                           help="Skip orphaned node cleanup after deletion")
        parser.add_argument("--debug", action="store_true", 
                           help="Debug mode: only delete the first node")
        
        args = parser.parse_args()
        
        report_file = args.report_file
        dry_run = args.dry_run
        priority_filter = args.priority
        backup = args.backup
        cleanup_orphans = not args.no_orphan_cleanup
        debug_mode = args.debug
    
    print("🗑️  Suspect Node Deletion Utility")
    print("=" * 40)
    
    # Create backup if requested
    if backup:
        backup_file = create_backup_before_deletion(report_file)
        print(f"Backup created: {backup_file}")
    
    # Perform deletion
    delete_suspect_nodes(
        report_filename=report_file,
        dry_run=dry_run,
        priority_filter=priority_filter,
        cleanup_orphans=cleanup_orphans,
        debug_mode=debug_mode
    )
