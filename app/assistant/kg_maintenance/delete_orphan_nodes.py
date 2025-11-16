"""
Delete Orphaned Nodes Utility
Finds and deletes nodes with no incoming or outgoing edges (orphans)
"""

import sys
from typing import List, Dict
from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def find_orphaned_nodes(session) -> List[Dict]:
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


def cleanup_orphaned_nodes(session, dry_run: bool = True, exclude_types: List[str] = None) -> Dict:
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


def main():
    """Main function for IDE execution"""
    print("🧹 Orphaned Nodes Cleanup Utility")
    print("=" * 40)
    print("This script finds and deletes nodes with no edges")
    print()
    
    # Get database session
    session = get_session()
    
    try:
        # First, show what orphaned nodes exist
        print("🔍 Scanning for orphaned nodes...")
        orphaned_nodes = find_orphaned_nodes(session)
        
        if not orphaned_nodes:
            print("✅ No orphaned nodes found! Your knowledge graph is clean.")
            return
        
        print(f"📊 Found {len(orphaned_nodes)} orphaned nodes:")
        for node in orphaned_nodes:
            print(f"  • {node['label']} ({node['type']})")
        
        print("\nOptions:")
        print("  1. Dry run (preview only) - default")
        print("  2. Delete all orphaned nodes")
        print("  3. Delete with custom exclusions")
        print("  4. Exit")
        
        choice = input("\nEnter choice (1-4, default=1): ").strip()
        
        if choice == "4":
            print("Exiting...")
            return
        elif choice == "2":
            # Delete all orphaned nodes
            result = cleanup_orphaned_nodes(session, dry_run=False)
        elif choice == "3":
            # Custom exclusions
            print("\nEnter node types to exclude (comma-separated, e.g., 'person,place'):")
            exclude_input = input("Exclude types (or press Enter for default 'person'): ").strip()
            if exclude_input:
                exclude_types = [t.strip() for t in exclude_input.split(',')]
            else:
                exclude_types = ['person']
            
            print(f"Excluding types: {exclude_types}")
            result = cleanup_orphaned_nodes(session, dry_run=False, exclude_types=exclude_types)
        else:
            # Default: dry run
            result = cleanup_orphaned_nodes(session, dry_run=True)
        
        # Show final results
        if result:
            print(f"\n🎯 FINAL RESULTS:")
            print(f"  Total orphaned nodes found: {result['total_orphans']}")
            print(f"  Nodes processed: {result['filtered_orphans']}")
            print(f"  Successfully deleted: {result['deleted']}")
            if result['errors']:
                print(f"  Errors: {len(result['errors'])}")
    
    except Exception as e:
        logger.error(f"Error in orphan cleanup: {e}")
        print(f"❌ Error: {e}")
    
    finally:
        session.close()


if __name__ == "__main__":
    main()
