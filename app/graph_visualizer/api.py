from flask import Blueprint, jsonify, request
from sqlalchemy.orm import Session
from app.assistant.kg_core.knowledge_graph_db_sqlite import Node, Edge, NODE_TYPES
from app.models.base import get_session
from datetime import datetime
from sqlalchemy import distinct, func
import chromadb

graph_api = Blueprint('graph_api', __name__)

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma_db")

@graph_api.route('/api/graph', methods=['GET'])
def get_graph_data():
    """Get all nodes and edges for graph visualization"""
    session = get_session()
    try:
        # Get all nodes from SQLite
        nodes = session.query(Node).all()
        node_data = []
        for node in nodes:
            node_data.append({
                'id': str(node.id),
                'label': node.label,
                'type': node.node_type,
                'category': node.category,
                'aliases': node.aliases if node.aliases else [],
                'description': node.description,
                'original_sentence': node.original_sentence,
                'attributes': node.attributes if node.attributes else {},
                'start_date': node.start_date.isoformat() if node.start_date else None,
                'end_date': node.end_date.isoformat() if node.end_date else None,
                'start_date_confidence': node.start_date_confidence,
                'end_date_confidence': node.end_date_confidence,
                'created_at': node.created_at.isoformat() if node.created_at else None,
                'updated_at': node.updated_at.isoformat() if node.updated_at else None,
                # Promoted fields
                'valid_during': node.valid_during,
                'hash_tags': node.hash_tags if node.hash_tags else [],
                'semantic_label': node.semantic_label,
                'goal_status': node.goal_status,
                # First-class fields
                'confidence': node.confidence,
                'importance': node.importance,
                'source': node.source,
                # Taxonomy paths (not implemented yet for SQLite version)
                'taxonomy_paths': []
            })
        
        # Get all edges from SQLite
        edges = session.query(Edge).all()
        edge_data = []
        for edge in edges:
            edge_data.append({
                'id': str(edge.id),
                'source_node': str(edge.source_id),
                'target_node': str(edge.target_id),
                'type': edge.relationship_type,
                'attributes': edge.attributes if edge.attributes else {},
                'original_message_id': edge.original_message_id,
                'sentence_id': edge.sentence_id,
                'relationship_descriptor': edge.relationship_descriptor,
                'sentence': edge.sentence,
                'original_message_timestamp': edge.original_message_timestamp.isoformat() if edge.original_message_timestamp else None,
                'created_at': edge.created_at.isoformat() if edge.created_at else None,
                'updated_at': edge.updated_at.isoformat() if edge.updated_at else None,
                # First-class fields
                'confidence': edge.confidence,
                'importance': edge.importance,
                'source': edge.source
            })
        
        # Debug logging
        print(f"🔍 API Debug: Returning {len(node_data)} nodes and {len(edge_data)} edges")
        print(f"📊 Node types: {list(set(n['type'] for n in node_data if n['type']))}")
        print(f"🔗 Edge types: {list(set(e['type'] for e in edge_data))}")
        
        # Check for orphaned edges
        node_ids = set(n['id'] for n in node_data)
        orphaned_edges = [e for e in edge_data if e['source_node'] not in node_ids or e['target_node'] not in node_ids]
        if orphaned_edges:
            print(f"⚠️ Found {len(orphaned_edges)} orphaned edges")
        
        return jsonify({
            'nodes': node_data,
            'edges': edge_data,
            'timestamp': datetime.utcnow().isoformat()
        })
    finally:
        session.close()

@graph_api.route('/api/graph/node-types', methods=['GET'])
def get_node_types():
    """Get all node types for filtering"""
    return jsonify([{
        'node_type': nt,
        'json_schema': {}
    } for nt in NODE_TYPES])

@graph_api.route('/api/graph/edge-types', methods=['GET'])
def get_edge_types():
    """Get all edge types for filtering"""
    session = get_session()
    try:
        # Get unique edge types from actual edges in the graph
        edge_types = session.query(distinct(Edge.relationship_type)).order_by(Edge.relationship_type).all()
        return jsonify([{
            'type_name': et[0],
            'json_schema': {}
        } for et in edge_types if et[0]])
    finally:
        session.close()

@graph_api.route('/api/graph/search', methods=['GET'])
def search_graph():
    """Search nodes and edges by label, type, or properties"""
    query = request.args.get('q', '').lower()
    node_type = request.args.get('node_type', '')
    edge_type = request.args.get('edge_type', '')
    
    session = get_session()
    try:
        # Search nodes
        node_query = session.query(Node)
        if query:
            node_query = node_query.filter(Node.label.ilike(f'%{query}%'))
        if node_type:
            node_query = node_query.filter(Node.node_type == node_type)
        
        nodes = node_query.all()
        node_data = [{
            'id': str(node.id),
            'label': node.label,
            'type': node.node_type,
            'category': node.category,
            'aliases': node.aliases if node.aliases else [],
            'description': node.description,
            'original_sentence': node.original_sentence,
            'attributes': node.attributes if node.attributes else {},
            'start_date': node.start_date.isoformat() if node.start_date else None,
            'end_date': node.end_date.isoformat() if node.end_date else None,
            'start_date_confidence': node.start_date_confidence,
            'end_date_confidence': node.end_date_confidence,
            'created_at': node.created_at.isoformat() if node.created_at else None,
            'updated_at': node.updated_at.isoformat() if node.updated_at else None,
            'valid_during': node.valid_during,
            'hash_tags': node.hash_tags if node.hash_tags else [],
            'semantic_label': node.semantic_label,
            'goal_status': node.goal_status,
            'confidence': node.confidence,
            'importance': node.importance,
            'source': node.source
        } for node in nodes]
        
        # Search edges
        edge_query = session.query(Edge)
        if query:
            edge_query = edge_query.filter(Edge.sentence.ilike(f'%{query}%'))
        if edge_type:
            edge_query = edge_query.filter(Edge.relationship_type == edge_type)
        
        edges = edge_query.all()
        edge_data = [{
            'id': str(edge.id),
            'source_node': str(edge.source_id),
            'target_node': str(edge.target_id),
            'type': edge.relationship_type,
            'attributes': edge.attributes if edge.attributes else {},
            'original_message_id': edge.original_message_id,
            'sentence_id': edge.sentence_id,
            'relationship_descriptor': edge.relationship_descriptor,
            'sentence': edge.sentence,
            'original_message_timestamp': edge.original_message_timestamp.isoformat() if edge.original_message_timestamp else None,
            'created_at': edge.created_at.isoformat() if edge.created_at else None,
            'updated_at': edge.updated_at.isoformat() if edge.updated_at else None,
            'confidence': edge.confidence,
            'importance': edge.importance,
            'source': edge.source
        } for edge in edges]
        
        return jsonify({
            'nodes': node_data,
            'edges': edge_data
        })
    finally:
        session.close()

@graph_api.route('/api/graph/node/<node_id>', methods=['GET'])
def get_node(node_id):
    """Get detailed information about a specific node"""
    session = get_session()
    try:
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Get connected edges
        outgoing = session.query(Edge).filter(Edge.source_id == node_id).all()
        incoming = session.query(Edge).filter(Edge.target_id == node_id).all()
        
        return jsonify({
            'node': {
                'id': str(node.id),
                'label': node.label,
                'type': node.node_type,
                'category': node.category,
                'aliases': node.aliases if node.aliases else [],
                'description': node.description,
                'original_sentence': node.original_sentence,
                'attributes': node.attributes if node.attributes else {},
                'start_date': node.start_date.isoformat() if node.start_date else None,
                'end_date': node.end_date.isoformat() if node.end_date else None,
                'created_at': node.created_at.isoformat() if node.created_at else None,
                'updated_at': node.updated_at.isoformat() if node.updated_at else None,
                'confidence': node.confidence,
                'importance': node.importance,
                'source': node.source
            },
            'outgoing_edges': len(outgoing),
            'incoming_edges': len(incoming)
        })
    finally:
        session.close()

@graph_api.route('/api/graph/edge/<edge_id>', methods=['GET'])
def get_edge(edge_id):
    """Get detailed information about a specific edge"""
    session = get_session()
    try:
        edge = session.query(Edge).filter(Edge.id == edge_id).first()
        if not edge:
            return jsonify({'error': 'Edge not found'}), 404
        
        return jsonify({
            'id': str(edge.id),
            'source_node': str(edge.source_id),
            'target_node': str(edge.target_id),
            'type': edge.relationship_type,
            'attributes': edge.attributes if edge.attributes else {},
            'sentence': edge.sentence,
            'created_at': edge.created_at.isoformat() if edge.created_at else None,
            'updated_at': edge.updated_at.isoformat() if edge.updated_at else None,
            'confidence': edge.confidence,
            'importance': edge.importance,
            'source': edge.source
        })
    finally:
        session.close()

@graph_api.route('/api/graph/stats', methods=['GET'])
def get_stats():
    """Get graph statistics"""
    session = get_session()
    try:
        total_nodes = session.query(Node).count()
        total_edges = session.query(Edge).count()
        
        # Node type distribution
        node_types = {}
        for nt in NODE_TYPES:
            count = session.query(Node).filter(Node.node_type == nt).count()
            if count > 0:
                node_types[nt] = count
        
        # Edge type distribution
        edge_types = session.query(Edge.relationship_type, func.count(Edge.id)).group_by(Edge.relationship_type).all()
        edge_type_dist = {et[0]: et[1] for et in edge_types if et[0]}
        
        return jsonify({
            'total_nodes': total_nodes,
            'total_edges': total_edges,
            'node_types': node_types,
            'edge_types': edge_type_dist
        })
    finally:
        session.close()

@graph_api.route('/api/graph/node/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    """Delete a node and its connected edges"""
    session = get_session()
    try:
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        # Delete connected edges first (CASCADE should handle this, but let's be explicit)
        session.query(Edge).filter((Edge.source_id == node_id) | (Edge.target_id == node_id)).delete()
        
        # Delete the node
        session.delete(node)
        session.commit()
        
        return jsonify({'message': 'Node deleted successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@graph_api.route('/api/graph/edge/<edge_id>', methods=['DELETE'])
def delete_edge(edge_id):
    """Delete an edge"""
    session = get_session()
    try:
        edge = session.query(Edge).filter(Edge.id == edge_id).first()
        if not edge:
            return jsonify({'error': 'Edge not found'}), 404
        
        session.delete(edge)
        session.commit()
        
        return jsonify({'message': 'Edge deleted successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@graph_api.route('/api/graph/node/<node_id>', methods=['PUT'])
def update_node(node_id):
    """Update node properties"""
    session = get_session()
    try:
        node = session.query(Node).filter(Node.id == node_id).first()
        if not node:
            return jsonify({'error': 'Node not found'}), 404
        
        data = request.json
        
        # Update allowed fields
        if 'label' in data:
            node.label = data['label']
        if 'description' in data:
            node.description = data['description']
        if 'category' in data:
            node.category = data['category']
        if 'aliases' in data:
            node.aliases = data['aliases']
        if 'attributes' in data:
            node.attributes = data['attributes']
        if 'confidence' in data:
            node.confidence = data['confidence']
        if 'importance' in data:
            node.importance = data['importance']
        if 'semantic_label' in data:
            node.semantic_label = data['semantic_label']
        
        node.updated_at = datetime.utcnow()
        session.commit()
        
        return jsonify({
            'id': str(node.id),
            'label': node.label,
            'type': node.node_type,
            'category': node.category,
            'aliases': node.aliases if node.aliases else [],
            'description': node.description,
            'attributes': node.attributes if node.attributes else {},
            'confidence': node.confidence,
            'importance': node.importance,
            'semantic_label': node.semantic_label,
            'updated_at': node.updated_at.isoformat() if node.updated_at else None
        })
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@graph_api.route('/api/graph/edge/<edge_id>', methods=['PUT'])
def update_edge(edge_id):
    """Update edge properties"""
    session = get_session()
    try:
        edge = session.query(Edge).filter(Edge.id == edge_id).first()
        if not edge:
            return jsonify({'error': 'Edge not found'}), 404
        
        data = request.json
        
        # Update allowed fields
        if 'relationship_type' in data:
            edge.relationship_type = data['relationship_type']
        if 'relationship_descriptor' in data:
            edge.relationship_descriptor = data['relationship_descriptor']
        if 'attributes' in data:
            edge.attributes = data['attributes']
        if 'sentence' in data:
            edge.sentence = data['sentence']
        if 'confidence' in data:
            edge.confidence = data['confidence']
        if 'importance' in data:
            edge.importance = data['importance']
        
        edge.updated_at = datetime.utcnow()
        session.commit()
        
        return jsonify({
            'id': str(edge.id),
            'source_node': str(edge.source_id),
            'target_node': str(edge.target_id),
            'type': edge.relationship_type,
            'relationship_descriptor': edge.relationship_descriptor,
            'attributes': edge.attributes if edge.attributes else {},
            'sentence': edge.sentence,
            'confidence': edge.confidence,
            'importance': edge.importance,
            'updated_at': edge.updated_at.isoformat() if edge.updated_at else None
        })
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()
