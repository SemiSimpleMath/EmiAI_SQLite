"""
Debug script to understand why important nodes are being filtered out
"""

from app.models.base import get_session
from app.assistant.kg_core.knowledge_graph_db import Node, Edge
from app.assistant.kg_rag_pipeline.kg_rag_pipeline import get_nodes_with_edges_and_importance, get_nodes_with_edges
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

def debug_node_importance(node_name: str, session):
    """Debug the importance calculation for a specific node"""
    print(f"\n🔍 Debugging node: {node_name}")
    
    # Find the node
    node = session.query(Node).filter(Node.label == node_name).first()
    if not node:
        print(f"❌ Node '{node_name}' not found")
        return
    
    # Check if it has outgoing edges
    outgoing_edges = session.query(Edge).filter(Edge.source_id == node.id).all()
    print(f"📊 Node has {len(outgoing_edges)} outgoing edges")
    
    if not outgoing_edges:
        print(f"❌ Node '{node_name}' has no outgoing edges - won't be processed")
        return
    
    # Calculate importance for each edge (using Edge.importance column)
    total_importance = 0
    print(f"\n📋 Edge details:")
    for i, edge in enumerate(outgoing_edges, 1):
        # Get importance: edge.attributes > Edge.importance column > default
        edge_importance = None
        if edge.attributes:
            edge_importance = edge.attributes.get("importance")
            if isinstance(edge_importance, str):
                try:
                    edge_importance = float(edge_importance)
                except ValueError:
                    edge_importance = None
        
        if edge_importance is None and edge.importance is not None:
            edge_importance = edge.importance
        
        if edge_importance is None:
            edge_importance = 0.5
        
        total_importance += edge_importance
        
        # Get target node info
        target_node = session.query(Node).filter(Node.id == edge.target_id).first()
        target_label = target_node.label if target_node else "Unknown"
        
        print(f"  {i}. {edge.relationship_type} -> {target_label}")
        print(f"     Importance: {edge_importance:.3f} (from: {'edge.attributes' if edge.attributes and edge.attributes.get('importance') else 'edge_type.json_schema' if edge_importance == type_importance.get(edge.relationship_type, 0.5) else 'default'})")
    
    avg_importance = total_importance / len(outgoing_edges)
    print(f"\n📊 Average importance: {avg_importance:.3f}")
    
    # Check different thresholds
    thresholds = [0.1, 0.3, 0.5, 0.7]
    print(f"\n🎯 Would be included with thresholds:")
    for threshold in thresholds:
        status = "✅ YES" if avg_importance >= threshold else "❌ NO"
        print(f"  {threshold}: {status}")

def debug_filtering():
    """Debug the filtering logic"""
    session = get_session()
    
    print("🔍 DEBUGGING ENTITY CARD PIPELINE FILTERING")
    print("=" * 50)
    
    # Test different filtering scenarios
    test_nodes = ["Mike Huckabee", "January full moon", "Dazzler"]  # Important people
    
    for node_name in test_nodes:
        debug_node_importance(node_name, session)
    
    print("\n" + "=" * 50)
    print("📊 FILTERING COMPARISON")
    print("=" * 50)
    
    # Compare different filtering approaches
    print("\n1. No importance filter (min_outgoing_edges=1):")
    nodes_basic = get_nodes_with_edges(session, 1)
    print(f"   Total nodes: {len(nodes_basic)}")
    important_nodes_basic = [n.label for n in nodes_basic if n.label in test_nodes]
    print(f"   Important nodes included: {important_nodes_basic}")
    
    print("\n2. With importance filter (min_importance=0.3):")
    nodes_03 = get_nodes_with_edges_and_importance(session, 1, 0.3)
    print(f"   Total nodes: {len(nodes_03)}")
    important_nodes_03 = [n.label for n in nodes_03 if n.label in test_nodes]
    print(f"   Important nodes included: {important_nodes_03}")
    
    print("\n3. With importance filter (min_importance=0.5):")
    nodes_05 = get_nodes_with_edges_and_importance(session, 1, 0.5)
    print(f"   Total nodes: {len(nodes_05)}")
    important_nodes_05 = [n.label for n in nodes_05 if n.label in test_nodes]
    print(f"   Important nodes included: {important_nodes_05}")
    
    print("\n4. With importance filter (min_importance=0.7):")
    nodes_07 = get_nodes_with_edges_and_importance(session, 1, 0.7)
    print(f"   Total nodes: {len(nodes_07)}")
    important_nodes_07 = [n.label for n in nodes_07 if n.label in test_nodes]
    print(f"   Important nodes included: {important_nodes_07}")
    
    session.close()

if __name__ == "__main__":
    debug_filtering()
