"""
Migration Script: Populate ChromaDB with Embeddings

This script generates embeddings for all existing nodes, edges, and taxonomy
entries and stores them in ChromaDB.

Run this once after implementing ChromaDB to populate the embedding cache.
"""

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db_sqlite import Node, Edge
from app.assistant.kg_core.taxonomy.models import Taxonomy
from app.assistant.kg_core.chroma_embedding_manager import get_chroma_manager
from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils
from tqdm import tqdm
import sys


def migrate_node_embeddings():
    """Generate and store embeddings for all nodes"""
    print("\n" + "="*80)
    print("MIGRATING NODE EMBEDDINGS TO CHROMADB")
    print("="*80)
    
    session = get_session()
    kg_utils = KnowledgeGraphUtils(session)
    chroma = get_chroma_manager()
    
    try:
        # Get all nodes
        nodes = session.query(Node).all()
        print(f"\nFound {len(nodes)} nodes to process")
        
        if len(nodes) == 0:
            print("No nodes found - skipping")
            return
        
        # Process each node
        success_count = 0
        error_count = 0
        
        for node in tqdm(nodes, desc="Processing nodes"):
            try:
                # Generate embedding
                embedding = kg_utils.create_embedding(node.label)
                
                # Store in ChromaDB
                chroma.store_node_embedding(str(node.id), node.label, embedding)
                success_count += 1
                
            except Exception as e:
                print(f"\n❌ Error processing node {node.id} ({node.label}): {e}")
                error_count += 1
        
        print(f"\n✅ Node migration complete:")
        print(f"   Success: {success_count}")
        print(f"   Errors: {error_count}")
        
    finally:
        session.close()


def migrate_edge_embeddings():
    """Generate and store embeddings for all edges with sentences"""
    print("\n" + "="*80)
    print("MIGRATING EDGE EMBEDDINGS TO CHROMADB")
    print("="*80)
    
    session = get_session()
    kg_utils = KnowledgeGraphUtils(session)
    chroma = get_chroma_manager()
    
    try:
        # Get all edges with sentences
        edges = session.query(Edge).filter(Edge.sentence.isnot(None)).all()
        print(f"\nFound {len(edges)} edges with sentences to process")
        
        if len(edges) == 0:
            print("No edges with sentences found - skipping")
            return
        
        # Process each edge
        success_count = 0
        error_count = 0
        
        for edge in tqdm(edges, desc="Processing edges"):
            try:
                # Generate embedding
                embedding = kg_utils.create_embedding(edge.sentence)
                
                # Store in ChromaDB
                chroma.store_edge_embedding(str(edge.id), edge.sentence, embedding)
                success_count += 1
                
            except Exception as e:
                print(f"\n❌ Error processing edge {edge.id}: {e}")
                error_count += 1
        
        print(f"\n✅ Edge migration complete:")
        print(f"   Success: {success_count}")
        print(f"   Errors: {error_count}")
        
    finally:
        session.close()


def migrate_taxonomy_embeddings():
    """Generate and store embeddings for all taxonomy entries"""
    print("\n" + "="*80)
    print("MIGRATING TAXONOMY EMBEDDINGS TO CHROMADB")
    print("="*80)
    
    session = get_session()
    kg_utils = KnowledgeGraphUtils(session)
    chroma = get_chroma_manager()
    
    try:
        # Get all taxonomy entries
        taxonomies = session.query(Taxonomy).all()
        print(f"\nFound {len(taxonomies)} taxonomy entries to process")
        
        if len(taxonomies) == 0:
            print("No taxonomy entries found - skipping")
            return
        
        # Process each taxonomy
        success_count = 0
        error_count = 0
        
        for taxonomy in tqdm(taxonomies, desc="Processing taxonomy"):
            try:
                # Generate embedding
                embedding = kg_utils.create_embedding(taxonomy.label)
                
                # Store in ChromaDB
                chroma.store_taxonomy_embedding(taxonomy.id, taxonomy.label, embedding)
                success_count += 1
                
            except Exception as e:
                print(f"\n❌ Error processing taxonomy {taxonomy.id} ({taxonomy.label}): {e}")
                error_count += 1
        
        print(f"\n✅ Taxonomy migration complete:")
        print(f"   Success: {success_count}")
        print(f"   Errors: {error_count}")
        
    finally:
        session.close()


def main():
    """Run all migrations"""
    print("\n" + "="*80)
    print("CHROMADB EMBEDDING MIGRATION")
    print("="*80)
    print("\nThis script will generate embeddings for all existing:")
    print("  - Nodes (label embeddings)")
    print("  - Edges (sentence embeddings)")
    print("  - Taxonomy (label embeddings)")
    print("\nThis may take a while depending on the size of your database.")
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("Migration cancelled")
        return
    
    try:
        # Migrate all embeddings
        migrate_node_embeddings()
        migrate_edge_embeddings()
        migrate_taxonomy_embeddings()
        
        # Show final stats
        chroma = get_chroma_manager()
        stats = chroma.get_stats()
        
        print("\n" + "="*80)
        print("MIGRATION COMPLETE")
        print("="*80)
        print(f"\nChromaDB Statistics:")
        print(f"  - Nodes: {stats['nodes']} embeddings")
        print(f"  - Edges: {stats['edges']} embeddings")
        print(f"  - Taxonomy: {stats['taxonomy']} embeddings")
        print(f"\n✅ All embeddings migrated successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

