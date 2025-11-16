"""
Setup script for standardization canonical and alias tables.

This creates the database tables for the new two-stage standardization system:
- label_canon: Canonical labels bucketed by node_type
- label_alias: Raw label → canonical mappings
- edge_canon: Canonical edge predicates bucketed by domain_type + range_type
- edge_alias: Raw predicate → canonical mappings
- review_queue: Uncertain cases requiring human review
"""

import app.assistant.tests.test_setup  # Initialize everything

from app.models.base import get_session, Base
from app.assistant.kg_core.models_standardization import (
    LabelCanon,
    LabelAlias,
    EdgeCanon,
    EdgeAlias,
    ReviewQueue
)

print("🔧 Creating standardization canonical and alias tables...")

session = get_session()
engine = session.bind

print(f"🔍 Database: {engine.url}")

# Create the tables
Base.metadata.create_all(
    engine, 
    tables=[
        LabelCanon.__table__,
        LabelAlias.__table__,
        EdgeCanon.__table__,
        EdgeAlias.__table__,
        ReviewQueue.__table__
    ], 
    checkfirst=True
)

session.close()

print("✅ Standardization tables created successfully!")
print("\n📊 Tables created:")
print("  - label_canon (canonical labels by node_type)")
print("  - label_alias (raw → canonical label mappings)")
print("  - edge_canon (canonical predicates by domain+range)")
print("  - edge_alias (raw → canonical predicate mappings)")
print("  - review_queue (uncertain cases for human review)")
print("\n💡 Next step: Run 'python seed_standardization_canonicals.py' to populate initial data")

