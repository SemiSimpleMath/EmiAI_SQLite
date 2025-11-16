"""
Knowledge Graph Extractor
Extracts node-edge-node relationships from the KG for RAG conversion
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.base import get_session
from app.assistant.kg_core.kg_tools import Node, Edge
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class KGExtractor:
    """Extracts node-edge-node relationships from the knowledge graph"""
    
    def __init__(self):
        self.session: Optional[Session] = None
    
    def get_all_relationships(self) -> List[Dict[str, Any]]:
        """
        Extract all node-edge-node relationships from the KG
        Returns list of relationship dictionaries
        """
        relationships = []
        
        try:
            session = get_session()
            # Get all edges with their connected nodes
            edges = session.query(Edge).all()
            
            for edge in edges:
                    # Get source and target nodes
                    source_node = session.query(Node).filter_by(id=edge.source_node_id).first()
                    target_node = session.query(Node).filter_by(id=edge.target_node_id).first()
                    
                    if source_node and target_node:
                        relationship = {
                            'edge_id': str(edge.id),
                            'source_node': {
                                'id': str(source_node.id),
                                'label': source_node.label,
                                'description': source_node.description,
                                'aliases': source_node.aliases or [],
                                'type': source_node.type
                            },
                            'target_node': {
                                'id': str(target_node.id),
                                'label': target_node.label,
                                'description': target_node.description,
                                'aliases': target_node.aliases or [],
                                'type': target_node.type
                            },
                            'edge': {
                                'type': edge.relationship_type,
                                'attributes': edge.attributes or {},
                                'context': edge.context,
                                'created_at': edge.created_at,
                                'updated_at': edge.updated_at
                            }
                        }
                        relationships.append(relationship)
                
            logger.info(f"Extracted {len(relationships)} relationships from KG")
            return relationships
                
        except Exception as e:
            logger.error(f"Error extracting relationships from KG: {e}")
            return []
    
    def get_relationships_by_type(self, edge_type: str) -> List[Dict[str, Any]]:
        """
        Extract relationships filtered by edge type
        """
        relationships = []
        
        try:
            session = get_session()
            edges = session.query(Edge).filter_by(relationship_type=edge_type).all()
                
            for edge in edges:
                source_node = session.query(Node).filter_by(id=edge.source_node_id).first()
                target_node = session.query(Node).filter_by(id=edge.target_node_id).first()
                
                if source_node and target_node:
                    relationship = {
                        'edge_id': str(edge.id),
                        'source_node': {
                            'id': str(source_node.id),
                            'label': source_node.label,
                            'description': source_node.description,
                            'aliases': source_node.aliases or [],
                            'type': source_node.type
                        },
                        'target_node': {
                            'id': str(target_node.id),
                            'label': target_node.label,
                            'description': target_node.description,
                            'aliases': target_node.aliases or [],
                            'type': target_node.type
                        },
                        'edge': {
                            'type': edge.relationship_type,
                            'attributes': edge.attributes or {},
                            'context': edge.context,
                            'created_at': edge.created_at,
                            'updated_at': edge.updated_at
                        }
                    }
                    relationships.append(relationship)
            
            logger.info(f"Extracted {len(relationships)} relationships of type '{edge_type}'")
            return relationships
                
        except Exception as e:
            logger.error(f"Error extracting relationships of type '{edge_type}': {e}")
            return []
    
    def get_relationships_by_node(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Extract all relationships involving a specific node
        """
        relationships = []
        
        try:
            session = get_session()
            # Get edges where the node is either source or target
            edges = session.query(Edge).filter(
                (Edge.source_node_id == node_id) | (Edge.target_node_id == node_id)
            ).all()
                
            for edge in edges:
                source_node = session.query(Node).filter_by(id=edge.source_node_id).first()
                target_node = session.query(Node).filter_by(id=edge.target_node_id).first()
                
                if source_node and target_node:
                    relationship = {
                        'edge_id': str(edge.id),
                        'source_node': {
                            'id': str(source_node.id),
                            'label': source_node.label,
                            'description': source_node.description,
                            'aliases': source_node.aliases or [],
                            'type': source_node.type
                        },
                        'target_node': {
                            'id': str(target_node.id),
                            'label': target_node.label,
                            'description': target_node.description,
                            'aliases': target_node.aliases or [],
                            'type': target_node.type
                        },
                        'edge': {
                            'type': edge.relationship_type,
                            'attributes': edge.attributes or {},
                            'context': edge.context,
                            'created_at': edge.created_at,
                            'updated_at': edge.updated_at
                        }
                    }
                    relationships.append(relationship)
            
            logger.info(f"Extracted {len(relationships)} relationships for node {node_id}")
            return relationships
                
        except Exception as e:
            logger.error(f"Error extracting relationships for node {node_id}: {e}")
            return []
