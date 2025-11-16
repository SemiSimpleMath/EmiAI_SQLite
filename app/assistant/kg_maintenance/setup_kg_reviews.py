#!/usr/bin/env python3
"""Setup script for kg_reviews table"""

import app.assistant.tests.test_setup  # Initialize everything

from app.models.base import get_session, Base
from app.assistant.kg_review.data_models.kg_review import KGReview

print("🔧 Creating kg_reviews table...")

# Get database session and engine
session = get_session()
engine = session.bind

print(f"🔍 Database: {engine.url}")

# Create the table
Base.metadata.create_all(engine, tables=[KGReview.__table__], checkfirst=True)

session.close()

print("✅ kg_reviews table created successfully!")
print("\n💡 Next step: Run 'python run_repair_pipeline.py' to generate reviews")

