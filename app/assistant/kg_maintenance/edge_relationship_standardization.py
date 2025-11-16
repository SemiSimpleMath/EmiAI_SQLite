"""
Edge Relationship Standardization Module
SQLite Compatible Version

This module provides a system for standardizing edge relationship names
that AI agents commonly guess incorrectly. It maps common variations and
mistakes to canonical relationship names used in the knowledge graph.
"""

import uuid
from typing import Dict, List, Optional, Tuple
from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, func, JSON

from app.models.base import Base, engine

# Helper to generate string UUIDs for SQLite
def generate_uuid():
    return str(uuid.uuid4())


class EdgeRelationshipMapping(Base):
    """
    Maps common AI agent relationship guesses to canonical relationship names.
    """
    __tablename__ = 'edge_relationship_mappings'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    
    # The common guess/variation that agents make
    guessed_relationship = Column(String, nullable=False, index=True)
    
    # The canonical relationship name to use
    canonical_relationship = Column(String, nullable=False, index=True)
    
    # Confidence score for this mapping (0.0 to 1.0)
    confidence_score = Column(Integer, nullable=False, default=100)  # Store as integer 0-100
    
    # Whether this mapping is currently active
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Description of when this mapping should be used
    description = Column(Text, nullable=True)
    
    # Examples of usage
    examples = Column(JSON, nullable=True)  # SQLite: List of example sentences
    
    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by = Column(String, nullable=True)  # Who created this mapping
    usage_count = Column(Integer, nullable=False, default=0)  # How many times this mapping was used
    
    # Tags for categorization
    tags = Column(JSON, nullable=True)  # SQLite: List of tags like ["family", "work", "location"]
    
    __table_args__ = (
        # Ensure unique combinations of guessed and canonical relationships
        # (allowing multiple guesses to map to same canonical)
    )


class EdgeRelationshipStandardizer:
    """
    Utility class for standardizing edge relationship names.
    """
    
    def __init__(self, session=None):
        from app.models.base import get_session
        self.session = session or get_session()
    
    def standardize_relationship(self, guessed_relationship: str, context: Optional[str] = None) -> Tuple[str, float]:
        """
        Standardize a guessed relationship name to its canonical form.
        
        Args:
            guessed_relationship: The relationship name guessed by an AI agent
            context: Optional context to help with disambiguation
            
        Returns:
            Tuple of (canonical_relationship, confidence_score)
        """
        # Normalize the input
        normalized_guess = self._normalize_relationship_name(guessed_relationship)
        
        # Look for exact match first
        mapping = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.guessed_relationship == normalized_guess,
            EdgeRelationshipMapping.is_active == True
        ).order_by(EdgeRelationshipMapping.confidence_score.desc()).first()
        
        if mapping:
            # Update usage count
            mapping.usage_count += 1
            self.session.commit()
            return mapping.canonical_relationship, mapping.confidence_score / 100.0
        
        # Look for partial matches (fuzzy matching)
        partial_matches = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.guessed_relationship.contains(normalized_guess),
            EdgeRelationshipMapping.is_active == True
        ).order_by(EdgeRelationshipMapping.confidence_score.desc()).limit(3).all()
        
        if partial_matches:
            # Return the highest confidence match
            best_match = partial_matches[0]
            best_match.usage_count += 1
            self.session.commit()
            return best_match.canonical_relationship, best_match.confidence_score / 100.0
        
        # If no match found, return the original with low confidence
        return guessed_relationship, 0.1
    
    def add_mapping(self, 
                   guessed_relationship: str, 
                   canonical_relationship: str, 
                   confidence_score: int = 100,
                   description: Optional[str] = None,
                   examples: Optional[List[str]] = None,
                   tags: Optional[List[str]] = None,
                   created_by: Optional[str] = None) -> EdgeRelationshipMapping:
        """
        Add a new relationship mapping.
        
        Args:
            guessed_relationship: The common guess/variation
            canonical_relationship: The standard relationship name
            confidence_score: Confidence score (0-100)
            description: Description of when to use this mapping
            examples: List of example sentences
            tags: List of tags for categorization
            created_by: Who created this mapping
            
        Returns:
            The created mapping object
        """
        # Edge types are now validated by the edge standardization system
        # No need to check EdgeType table (it no longer exists)
        
        # Create the mapping
        mapping = EdgeRelationshipMapping(
            guessed_relationship=self._normalize_relationship_name(guessed_relationship),
            canonical_relationship=canonical_relationship,
            confidence_score=confidence_score,
            description=description,
            examples=examples or [],
            tags=tags or [],
            created_by=created_by
        )
        
        self.session.add(mapping)
        self.session.commit()
        return mapping
    
    def get_all_mappings(self, active_only: bool = True) -> List[EdgeRelationshipMapping]:
        """
        Get all relationship mappings.
        
        Args:
            active_only: Whether to return only active mappings
            
        Returns:
            List of mapping objects
        """
        query = self.session.query(EdgeRelationshipMapping)
        if active_only:
            query = query.filter(EdgeRelationshipMapping.is_active == True)
        return query.order_by(EdgeRelationshipMapping.usage_count.desc()).all()
    
    def get_mappings_by_tag(self, tag: str, active_only: bool = True) -> List[EdgeRelationshipMapping]:
        """
        Get mappings filtered by tag.
        
        Args:
            tag: Tag to filter by
            active_only: Whether to return only active mappings
            
        Returns:
            List of mapping objects
        """
        query = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.tags.contains([tag])
        )
        if active_only:
            query = query.filter(EdgeRelationshipMapping.is_active == True)
        return query.order_by(EdgeRelationshipMapping.usage_count.desc()).all()
    
    def deactivate_mapping(self, mapping_id: uuid.UUID) -> bool:
        """
        Deactivate a mapping.
        
        Args:
            mapping_id: ID of the mapping to deactivate
            
        Returns:
            True if successful, False if mapping not found
        """
        mapping = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.id == mapping_id
        ).first()
        
        if mapping:
            mapping.is_active = False
            self.session.commit()
            return True
        return False
    
    def update_confidence(self, mapping_id: uuid.UUID, new_confidence: int) -> bool:
        """
        Update the confidence score of a mapping.
        
        Args:
            mapping_id: ID of the mapping to update
            new_confidence: New confidence score (0-100)
            
        Returns:
            True if successful, False if mapping not found
        """
        mapping = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.id == mapping_id
        ).first()
        
        if mapping:
            mapping.confidence_score = max(0, min(100, new_confidence))
            self.session.commit()
            return True
        return False
    
    def _normalize_relationship_name(self, relationship: str) -> str:
        """
        Normalize a relationship name for consistent matching.
        
        Args:
            relationship: The relationship name to normalize
            
        Returns:
            Normalized relationship name
        """
        # Convert to lowercase
        normalized = relationship.lower().strip()
        
        # Remove common prefixes/suffixes that don't affect meaning
        normalized = normalized.replace('_', ' ')
        normalized = ' '.join(normalized.split())  # Normalize whitespace
        normalized = normalized.replace(' ', '_')
        
        return normalized
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the relationship mappings.
        
        Returns:
            Dictionary with statistics
        """
        total_mappings = self.session.query(EdgeRelationshipMapping).count()
        active_mappings = self.session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.is_active == True
        ).count()
        
        # Get most used mappings
        most_used = self.session.query(EdgeRelationshipMapping).order_by(
            EdgeRelationshipMapping.usage_count.desc()
        ).limit(10).all()
        
        # Get unique canonical relationships
        unique_canonical = self.session.query(
            EdgeRelationshipMapping.canonical_relationship
        ).distinct().count()
        
        return {
            'total_mappings': total_mappings,
            'active_mappings': active_mappings,
            'unique_canonical_relationships': unique_canonical,
            'most_used_mappings': [
                {
                    'guessed': m.guessed_relationship,
                    'canonical': m.canonical_relationship,
                    'usage_count': m.usage_count,
                    'confidence': m.confidence_score
                }
                for m in most_used
            ]
        }


def initialize_standard_mappings():
    """
    Initialize the database with common relationship mappings.
    """
    from app.models.base import get_session
    session = get_session()
    standardizer = EdgeRelationshipStandardizer(session)
    
    # Common family relationships
    family_mappings = [
        # Marriage relationships
        ("is_married_to", "married_to", 100, "Marriage relationship"),
        ("married_to", "married_to", 100, "Direct marriage relationship"),
        ("has_spouse", "married_to", 95, "Spouse relationship"),
        ("spouse_of", "married_to", 95, "Spouse relationship"),
        
        # Parent-child relationships
        ("is_parent_of", "parent_of", 100, "Parent-child relationship"),
        ("has_child", "parent_of", 95, "Parent-child relationship"),
        ("father_of", "parent_of", 90, "Father-child relationship"),
        ("mother_of", "parent_of", 90, "Mother-child relationship"),
        
        # Child-parent relationships
        ("child_of", "child_of", 100, "Child-parent relationship"),
        ("is_child_of", "child_of", 100, "Child-parent relationship"),
        ("son_of", "child_of", 90, "Son-parent relationship"),
        ("daughter_of", "child_of", 90, "Daughter-parent relationship"),
        
        # Sibling relationships
        ("has_sibling", "sibling_of", 95, "Sibling relationship"),
        ("is_sibling_of", "sibling_of", 100, "Sibling relationship"),
        ("brother_of", "sibling_of", 90, "Brother relationship"),
        ("sister_of", "sibling_of", 90, "Sister relationship"),
    ]
    
    # Work relationships
    work_mappings = [
        # Employment relationships
        ("works_for", "works_for", 100, "Employment relationship"),
        ("employed_by", "works_for", 95, "Employment relationship"),
        ("employee_of", "works_for", 95, "Employment relationship"),
        ("is_employed_by", "works_for", 95, "Employment relationship"),
        
        # Location-based work relationships
        ("works_at", "works_at", 100, "Work location relationship"),
        ("works_in", "works_at", 95, "Work location relationship"),
        ("based_at", "works_at", 90, "Work location relationship"),
        
        # Management relationships
        ("manages", "manages", 100, "Management relationship"),
        ("is_manager_of", "manages", 95, "Management relationship"),
        ("supervises", "manages", 95, "Management relationship"),
        
        # Reporting relationships
        ("reports_to", "reports_to", 100, "Reporting relationship"),
        ("supervised_by", "reports_to", 95, "Reporting relationship"),
        ("reports_to_manager", "reports_to", 90, "Reporting relationship"),
    ]
    
    # Location relationships
    location_mappings = [
        # Residence relationships
        ("lives_in", "lives_in", 100, "Residence relationship"),
        ("resides_in", "lives_in", 95, "Residence relationship"),
        ("lives_at", "lives_in", 90, "Residence relationship"),
        ("resides_at", "lives_in", 90, "Residence relationship"),
        
        # General location relationships
        ("located_in", "located_in", 100, "General location relationship"),
        ("is_located_in", "located_in", 95, "General location relationship"),
        ("situated_in", "located_in", 95, "General location relationship"),
        
        # Organization base relationships
        ("based_in", "based_in", 100, "Organization base location"),
        ("headquartered_in", "based_in", 95, "Organization headquarters"),
        ("has_headquarters_in", "based_in", 90, "Organization headquarters"),
    ]
    
    # Possession relationships
    possession_mappings = [
        ("has", "has", 100, "Possession relationship"),
        ("owns", "has", 95, "Possession relationship"),
        ("possesses", "has", 95, "Possession relationship"),
        ("has_phone", "has_phone", 100, "Phone possession"),
        ("has_email", "has_email", 100, "Email possession"),
        ("has_address", "has_address", 100, "Address possession"),
    ]
    
    # Knowledge/interest relationships
    knowledge_mappings = [
        ("knows", "knows", 100, "Knowledge relationship"),
        ("knows_about", "knows", 95, "Knowledge relationship"),
        ("is_familiar_with", "knows", 90, "Knowledge relationship"),
        ("likes", "likes", 100, "Preference relationship"),
        ("enjoys", "likes", 95, "Preference relationship"),
        ("interested_in", "interested_in", 100, "Interest relationship"),
        ("studies", "studies", 100, "Study relationship"),
        ("learns", "studies", 95, "Study relationship"),
    ]
    
    # Combine all mappings
    all_mappings = (
        family_mappings + work_mappings + location_mappings + 
        possession_mappings + knowledge_mappings
    )
    
    # Add mappings to database
    for guessed, canonical, confidence, description in all_mappings:
        # Check if mapping already exists
        existing = session.query(EdgeRelationshipMapping).filter(
            EdgeRelationshipMapping.guessed_relationship == guessed,
            EdgeRelationshipMapping.canonical_relationship == canonical
        ).first()
        
        if not existing:
            standardizer.add_mapping(
                guessed_relationship=guessed,
                canonical_relationship=canonical,
                confidence_score=confidence,
                description=description,
                created_by="system_initialization"
            )
    
    session.close()
    print("✅ Standard relationship mappings initialized successfully!")


def create_edge_relationship_tables():
    """
    Create the edge relationship standardization tables.
    """
    Base.metadata.create_all(engine, tables=[EdgeRelationshipMapping.__table__], checkfirst=True)
    print("✅ Edge relationship standardization tables created successfully!")


if __name__ == "__main__":
    # Create tables and initialize with standard mappings
    create_edge_relationship_tables()
    initialize_standard_mappings()
