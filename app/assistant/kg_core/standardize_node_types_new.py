#!/usr/bin/env python3
"""
Standardize node types in the new _new tables to use consistent naming.
Converts: Entity, StateNode, EventNode, GoalNode, PropertyNode, ConceptNode
To:      Entity, State, Event, Goal, Property, Concept
"""

import os
import sys
from sqlalchemy import text

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.base import get_session

def standardize_node_types():
    """Standardize node types to consistent naming"""
    session = get_session()
    engine = session.bind
    
    try:
        print("🔄 Starting node type standardization for _new tables...")
        
        # Step 1: Check current node types
        print("📋 Step 1: Checking current node types...")
        
        check_types_sql = """
        SELECT node_type, COUNT(*) as count
        FROM nodes_new 
        GROUP BY node_type 
        ORDER BY count DESC;
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(check_types_sql))
            current_types = result.fetchall()
            
            print("📊 Current node types in nodes_new:")
            for node_type, count in current_types:
                print(f"   {node_type}: {count} nodes")
        
        # Step 2: Add new standardized node types to node_types_new
        print("📋 Step 2: Adding standardized node types...")
        
        add_types_sql = """
        INSERT INTO node_types_new (type_name, json_schema) VALUES
        ('Entity', '{}'),
        ('State', '{}'),
        ('Event', '{}'),
        ('Goal', '{}'),
        ('Property', '{}'),
        ('Concept', '{}')
        ON CONFLICT (type_name) DO NOTHING;
        """
        
        with engine.connect() as conn:
            conn.execute(text(add_types_sql))
            conn.commit()
        print("✅ Added standardized node types")
        
        # Step 3: Update nodes to use standardized types
        print("📋 Step 3: Updating nodes to use standardized types...")
        
        update_nodes_sql = """
        -- Update nodes to use standardized type names
        UPDATE nodes_new SET node_type = 'Entity' WHERE node_type = 'Entity';
        UPDATE nodes_new SET node_type = 'State' WHERE node_type = 'StateNode';
        UPDATE nodes_new SET node_type = 'Event' WHERE node_type = 'EventNode';
        UPDATE nodes_new SET node_type = 'Goal' WHERE node_type = 'GoalNode';
        UPDATE nodes_new SET node_type = 'Property' WHERE node_type = 'PropertyNode';
        UPDATE nodes_new SET node_type = 'Concept' WHERE node_type = 'ConceptNode';
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(update_nodes_sql))
            conn.commit()
        print("✅ Updated nodes to use standardized types")
        
        # Step 4: Update edges to use standardized types (if they reference node types)
        print("📋 Step 4: Checking if edges need type updates...")
        
        # Check if edges table has type_name column that references node types
        check_edges_sql = """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'edges_new' 
        AND column_name = 'type_name';
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(check_edges_sql))
            edges_has_type = result.fetchone()
            
            if edges_has_type:
                print("📊 Edges table has type_name column, updating...")
                
                update_edges_sql = """
                UPDATE edges_new SET type_name = 'Entity' WHERE type_name = 'Entity';
                UPDATE edges_new SET type_name = 'State' WHERE type_name = 'StateNode';
                UPDATE edges_new SET type_name = 'Event' WHERE type_name = 'EventNode';
                UPDATE edges_new SET type_name = 'Goal' WHERE type_name = 'GoalNode';
                UPDATE edges_new SET type_name = 'Property' WHERE type_name = 'PropertyNode';
                UPDATE edges_new SET type_name = 'Concept' WHERE type_name = 'ConceptNode';
                """
                
                conn.execute(text(update_edges_sql))
                conn.commit()
                print("✅ Updated edges to use standardized types")
            else:
                print("📊 Edges table doesn't have type_name column, skipping")
        
        # Step 5: Clean up old node types (optional - keep them for reference)
        print("📋 Step 5: Checking for old node types to clean up...")
        
        cleanup_types_sql = """
        SELECT type_name 
        FROM node_types_new 
        WHERE type_name IN ('StateNode', 'EventNode', 'GoalNode', 'PropertyNode', 'ConceptNode');
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(cleanup_types_sql))
            old_types = result.fetchall()
            
            if old_types:
                print(f"📊 Found {len(old_types)} old node types that could be cleaned up:")
                for (type_name,) in old_types:
                    print(f"   - {type_name}")
                print("   (Keeping them for now - can be removed later if not needed)")
            else:
                print("📊 No old node types found to clean up")
        
        # Step 6: Verify the standardization
        print("📋 Step 6: Verifying standardization...")
        
        verify_sql = """
        SELECT node_type, COUNT(*) as count
        FROM nodes_new 
        GROUP BY node_type 
        ORDER BY count DESC;
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(verify_sql))
            standardized_types = result.fetchall()
            
            print("📊 Standardized node types in nodes_new:")
            for node_type, count in standardized_types:
                print(f"   {node_type}: {count} nodes")
        
        # Step 7: Show sample of each type
        print("📋 Step 7: Sample nodes of each type...")
        
        for node_type, _ in standardized_types:
            sample_sql = text("""
                SELECT label, node_type, description
                FROM nodes_new 
                WHERE node_type = :node_type
                LIMIT 3;
            """)
            
            with engine.connect() as conn:
                result = conn.execute(sample_sql, {'node_type': node_type})
                samples = result.fetchall()
                
                print(f"\n📋 Sample {node_type} nodes:")
                for i, (label, ntype, description) in enumerate(samples, 1):
                    desc_preview = description[:50] + "..." if description and len(description) > 50 else description
                    print(f"   {i}. {label} - {desc_preview}")
        
        print("\n🎉 Node type standardization completed successfully!")
        print("   - Standardized to: Entity, State, Event, Goal, Property, Concept")
        print("   - Updated all nodes and edges to use new type names")
        print("   - Added new type definitions to node_types_new")
        print("   - Old type definitions preserved for reference")
        
    except Exception as e:
        print(f"❌ Error during standardization: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    standardize_node_types()
