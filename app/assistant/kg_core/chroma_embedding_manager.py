"""
ChromaDB Embedding Manager

Centralized manager for storing and retrieving embeddings in ChromaDB.
This replaces the embedding columns that were removed from SQLite models.

Collections:
- node_embeddings: Node label embeddings (keyed by node.id)
- edge_embeddings: Edge sentence embeddings (keyed by edge.id)
- taxonomy_embeddings: Taxonomy label embeddings (keyed by taxonomy.id)
"""

import chromadb
from chromadb.config import Settings
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import numpy as np
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class ChromaEmbeddingManager:
    """Manages embeddings in ChromaDB for KG nodes, edges, and taxonomy"""
    
    _instance = None
    _client = None
    
    def __new__(cls):
        """Singleton pattern to ensure one ChromaDB client"""
        if cls._instance is None:
            cls._instance = super(ChromaEmbeddingManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize ChromaDB client and collections"""
        if self._client is None:
            # Initialize ChromaDB client
            chroma_path = Path("./chroma_db")
            chroma_path.mkdir(exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info(f"ChromaDB initialized at {chroma_path}")
            
            # Initialize collections
            self._init_collections()
    
    def _init_collections(self):
        """Initialize or get existing collections"""
        try:
            # Node embeddings
            self.node_collection = self._client.get_or_create_collection(
                name="node_embeddings",
                metadata={"description": "Node label embeddings"}
            )
            
            # Edge embeddings
            self.edge_collection = self._client.get_or_create_collection(
                name="edge_embeddings",
                metadata={"description": "Edge sentence embeddings"}
            )
            
            # Taxonomy embeddings
            self.taxonomy_collection = self._client.get_or_create_collection(
                name="taxonomy_embeddings",
                metadata={"description": "Taxonomy label embeddings"}
            )
            
            logger.info(f"ChromaDB collections initialized:")
            logger.info(f"  - node_embeddings: {self.node_collection.count()} items")
            logger.info(f"  - edge_embeddings: {self.edge_collection.count()} items")
            logger.info(f"  - taxonomy_embeddings: {self.taxonomy_collection.count()} items")
            
        except Exception as e:
            logger.error(f"Error initializing ChromaDB collections: {e}")
            raise
    
    # ==================== NODE EMBEDDINGS ====================
    
    def store_node_embedding(self, node_id: str, label: str, embedding: List[float]):
        """Store a node's label embedding"""
        try:
            self.node_collection.upsert(
                ids=[str(node_id)],
                embeddings=[embedding],
                metadatas=[{"label": label}]
            )
            logger.debug(f"Stored embedding for node {node_id}: {label}")
        except Exception as e:
            logger.error(f"Error storing node embedding: {e}")
            raise
    
    def get_node_embedding(self, node_id: str) -> Optional[List[float]]:
        """Get a node's label embedding"""
        try:
            result = self.node_collection.get(
                ids=[str(node_id)],
                include=["embeddings"]
            )
            
            if result['embeddings'] and len(result['embeddings']) > 0:
                return result['embeddings'][0]
            return None
        except Exception as e:
            logger.debug(f"Node embedding not found for {node_id}: {e}")
            return None
    
    def search_similar_nodes(
        self, 
        query_embedding: List[float], 
        k: int = 10,
        threshold: float = 0.0
    ) -> List[Tuple[str, float, str]]:
        """
        Search for similar nodes by embedding
        
        Returns:
            List of (node_id, similarity_score, label)
        """
        try:
            results = self.node_collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["metadatas", "distances"]
            )
            
            if not results['ids'] or len(results['ids']) == 0:
                return []
            
            # Convert distances to similarities (ChromaDB returns L2 distances)
            # similarity = 1 / (1 + distance)
            similar_nodes = []
            for node_id, distance, metadata in zip(
                results['ids'][0],
                results['distances'][0],
                results['metadatas'][0]
            ):
                similarity = 1 / (1 + distance)
                if similarity >= threshold:
                    label = metadata.get('label', '')
                    similar_nodes.append((node_id, similarity, label))
            
            return similar_nodes
        except Exception as e:
            logger.error(f"Error searching similar nodes: {e}")
            return []
    
    def delete_node_embedding(self, node_id: str):
        """Delete a node's embedding"""
        try:
            self.node_collection.delete(ids=[str(node_id)])
            logger.debug(f"Deleted embedding for node {node_id}")
        except Exception as e:
            logger.error(f"Error deleting node embedding: {e}")
    
    # ==================== EDGE EMBEDDINGS ====================
    
    def store_edge_embedding(self, edge_id: str, sentence: str, embedding: List[float]):
        """Store an edge's sentence embedding"""
        try:
            self.edge_collection.upsert(
                ids=[str(edge_id)],
                embeddings=[embedding],
                metadatas=[{"sentence": sentence[:500]}]  # Truncate long sentences
            )
            logger.debug(f"Stored embedding for edge {edge_id}")
        except Exception as e:
            logger.error(f"Error storing edge embedding: {e}")
            raise
    
    def get_edge_embedding(self, edge_id: str) -> Optional[List[float]]:
        """Get an edge's sentence embedding"""
        try:
            result = self.edge_collection.get(
                ids=[str(edge_id)],
                include=["embeddings"]
            )
            
            if result['embeddings'] and len(result['embeddings']) > 0:
                return result['embeddings'][0]
            return None
        except Exception as e:
            logger.debug(f"Edge embedding not found for {edge_id}: {e}")
            return None
    
    def search_similar_edges(
        self,
        query_embedding: List[float],
        k: int = 10,
        threshold: float = 0.0
    ) -> List[Tuple[str, float]]:
        """
        Search for similar edges by embedding
        
        Returns:
            List of (edge_id, similarity_score)
        """
        try:
            results = self.edge_collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["distances"]
            )
            
            if not results['ids'] or len(results['ids']) == 0:
                return []
            
            similar_edges = []
            for edge_id, distance in zip(results['ids'][0], results['distances'][0]):
                similarity = 1 / (1 + distance)
                if similarity >= threshold:
                    similar_edges.append((edge_id, similarity))
            
            return similar_edges
        except Exception as e:
            logger.error(f"Error searching similar edges: {e}")
            return []
    
    def delete_edge_embedding(self, edge_id: str):
        """Delete an edge's embedding"""
        try:
            self.edge_collection.delete(ids=[str(edge_id)])
            logger.debug(f"Deleted embedding for edge {edge_id}")
        except Exception as e:
            logger.error(f"Error deleting edge embedding: {e}")
    
    # ==================== TAXONOMY EMBEDDINGS ====================
    
    def store_taxonomy_embedding(self, taxonomy_id: int, label: str, embedding: List[float]):
        """Store a taxonomy's label embedding"""
        try:
            self.taxonomy_collection.upsert(
                ids=[str(taxonomy_id)],
                embeddings=[embedding],
                metadatas=[{"label": label}]
            )
            logger.debug(f"Stored embedding for taxonomy {taxonomy_id}: {label}")
        except Exception as e:
            logger.error(f"Error storing taxonomy embedding: {e}")
            raise
    
    def get_taxonomy_embedding(self, taxonomy_id: int) -> Optional[List[float]]:
        """Get a taxonomy's label embedding"""
        try:
            result = self.taxonomy_collection.get(
                ids=[str(taxonomy_id)],
                include=["embeddings"]
            )
            
            if result['embeddings'] and len(result['embeddings']) > 0:
                return result['embeddings'][0]
            return None
        except Exception as e:
            logger.debug(f"Taxonomy embedding not found for {taxonomy_id}: {e}")
            return None
    
    def search_similar_taxonomy(
        self,
        query_embedding: List[float],
        k: int = 10,
        threshold: float = 0.0
    ) -> List[Tuple[int, float, str]]:
        """
        Search for similar taxonomy types by embedding
        
        Returns:
            List of (taxonomy_id, similarity_score, label)
        """
        try:
            results = self.taxonomy_collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["metadatas", "distances"]
            )
            
            if not results['ids'] or len(results['ids']) == 0:
                return []
            
            similar_taxonomy = []
            for tax_id, distance, metadata in zip(
                results['ids'][0],
                results['distances'][0],
                results['metadatas'][0]
            ):
                similarity = 1 / (1 + distance)
                if similarity >= threshold:
                    label = metadata.get('label', '')
                    similar_taxonomy.append((int(tax_id), similarity, label))
            
            return similar_taxonomy
        except Exception as e:
            logger.error(f"Error searching similar taxonomy: {e}")
            return []
    
    def delete_taxonomy_embedding(self, taxonomy_id: int):
        """Delete a taxonomy's embedding"""
        try:
            self.taxonomy_collection.delete(ids=[str(taxonomy_id)])
            logger.debug(f"Deleted embedding for taxonomy {taxonomy_id}")
        except Exception as e:
            logger.error(f"Error deleting taxonomy embedding: {e}")
    
    # ==================== UTILITY METHODS ====================
    
    def reset_all(self):
        """Delete all embeddings (use with caution!)"""
        logger.warning("Resetting all ChromaDB collections...")
        self._client.delete_collection("node_embeddings")
        self._client.delete_collection("edge_embeddings")
        self._client.delete_collection("taxonomy_embeddings")
        self._init_collections()
        logger.info("All ChromaDB collections reset")
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about stored embeddings"""
        return {
            "nodes": self.node_collection.count(),
            "edges": self.edge_collection.count(),
            "taxonomy": self.taxonomy_collection.count()
        }


# Global singleton instance
_chroma_manager = None

def get_chroma_manager() -> ChromaEmbeddingManager:
    """Get the global ChromaDB manager instance"""
    global _chroma_manager
    if _chroma_manager is None:
        _chroma_manager = ChromaEmbeddingManager()
    return _chroma_manager

