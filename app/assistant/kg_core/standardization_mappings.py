"""
Standardization Mappings Database Models

These tables store learned mappings from unstandardized to standardized forms,
building up a dictionary over time as the standardizer agents process data.
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Index
from datetime import datetime, timezone
from app.models.base import Base


class NodeLabelMapping(Base):
    """
    Stores mappings from unstandardized node labels to standardized forms.
    
    Examples:
    - "Jukka" → "jukka"
    - "NY" → "new york"
    - "DiCaprio" → "leonardo dicaprio"
    """
    __tablename__ = 'node_label_mappings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The mapping
    unstandardized = Column(String, nullable=False, index=True)
    standardized = Column(String, nullable=False)
    
    # Metadata
    usage_count = Column(Integer, nullable=False, default=1)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Quality control
    is_verified = Column(Boolean, nullable=False, default=False)  # Human verified
    confidence = Column(Integer, nullable=False, default=1)  # How confident we are (1-10)
    
    # Context for review
    example_context = Column(String, nullable=True)  # Example sentence where this was used
    agent_reasoning = Column(String, nullable=True)  # Why the agent made this mapping
    
    # Indexes for fast lookup
    __table_args__ = (
        Index('ix_node_label_unstd_std', 'unstandardized', 'standardized'),
        Index('ix_node_label_unstd', 'unstandardized'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'unstandardized': self.unstandardized,
            'standardized': self.standardized,
            'usage_count': self.usage_count,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'is_verified': self.is_verified,
            'confidence': self.confidence,
            'example_context': self.example_context,
            'agent_reasoning': self.agent_reasoning
        }


class SemanticLabelMapping(Base):
    """
    Stores mappings from unstandardized semantic labels to standardized forms.
    
    Examples:
    - "Software Engineer" → "engineer"
    - "Tech Startup" → "company"
    - "Birthday Party" → "social event"
    """
    __tablename__ = 'semantic_label_mappings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The mapping
    unstandardized = Column(String, nullable=False, index=True)
    standardized = Column(String, nullable=False)
    
    # Context (semantic labels are context-dependent on node_type)
    node_type = Column(String, nullable=True)  # person, entity, event, etc.
    
    # Metadata
    usage_count = Column(Integer, nullable=False, default=1)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Quality control
    is_verified = Column(Boolean, nullable=False, default=False)
    confidence = Column(Integer, nullable=False, default=1)
    
    # Context for review
    example_context = Column(String, nullable=True)
    agent_reasoning = Column(String, nullable=True)
    
    # Indexes for fast lookup
    __table_args__ = (
        Index('ix_semantic_label_unstd_std', 'unstandardized', 'standardized'),
        Index('ix_semantic_label_unstd_type', 'unstandardized', 'node_type'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'unstandardized': self.unstandardized,
            'standardized': self.standardized,
            'node_type': self.node_type,
            'usage_count': self.usage_count,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'is_verified': self.is_verified,
            'confidence': self.confidence,
            'example_context': self.example_context,
            'agent_reasoning': self.agent_reasoning
        }


class RelationshipTypeMapping(Base):
    """
    Stores mappings from unstandardized relationship types to canonical forms.
    
    Examples:
    - "employed_by" → "works_for"
    - "lives_in" → "located_in"
    - "WorksFor" → "works_for"
    """
    __tablename__ = 'relationship_type_mappings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The mapping
    unstandardized = Column(String, nullable=False, index=True)
    standardized = Column(String, nullable=False)
    
    # Metadata
    usage_count = Column(Integer, nullable=False, default=1)
    first_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Quality control
    is_verified = Column(Boolean, nullable=False, default=False)
    confidence = Column(Integer, nullable=False, default=1)
    
    # Context for review
    example_context = Column(String, nullable=True)  # Example: "jukka works_for google"
    agent_reasoning = Column(String, nullable=True)
    
    # Indexes for fast lookup
    __table_args__ = (
        Index('ix_relationship_type_unstd_std', 'unstandardized', 'standardized'),
        Index('ix_relationship_type_unstd', 'unstandardized'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'unstandardized': self.unstandardized,
            'standardized': self.standardized,
            'usage_count': self.usage_count,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'is_verified': self.is_verified,
            'confidence': self.confidence,
            'example_context': self.example_context,
            'agent_reasoning': self.agent_reasoning
        }

