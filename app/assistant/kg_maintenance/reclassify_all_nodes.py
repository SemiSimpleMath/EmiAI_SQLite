#!/usr/bin/env python3
"""
Reclassify All Nodes
Removes all node taxonomy classifications so they can be re-classified with improved classifiers.
"""
import app.assistant.tests.test_setup
from app.models.base import get_session
from app.assistant.kg_core.taxonomy.models import NodeTaxonomyLink, NodeTaxonomyReviewQueue, TaxonomySuggestions


def reclassify_all():
    """Remove all node classifications and review queue entries"""
    session = get_session()
    
    try:
        # Count current state
        link_count = session.query(NodeTaxonomyLink).count()
        review_count = session.query(NodeTaxonomyReviewQueue).count()
        suggestion_count = session.query(TaxonomySuggestions).count()
        
        print("\n" + "="*80)
        print("🔄 RECLASSIFY ALL NODES")
        print("="*80)
        print(f"\nCurrent state:")
        print(f"  📊 {link_count:,} node classifications")
        print(f"  📝 {review_count:,} pending reviews")
        print(f"  💡 {suggestion_count:,} taxonomy suggestions")
        
        # Confirm
        print(f"\n⚠️  This will DELETE all of the above and reclassify all nodes.")
        response = input("\nContinue? (type 'yes' to proceed): ")
        
        if response.lower() != 'yes':
            print("\n❌ Aborted. No changes made.")
            return
        
        # Delete all classifications
        print("\n🗑️  Deleting node classifications...")
        deleted_links = session.query(NodeTaxonomyLink).delete()
        print(f"   ✅ Deleted {deleted_links:,} node-taxonomy links")
        
        # Delete all review queue entries
        print("\n🗑️  Clearing review queue...")
        deleted_reviews = session.query(NodeTaxonomyReviewQueue).delete()
        print(f"   ✅ Deleted {deleted_reviews:,} review queue entries")
        
        # Delete all taxonomy suggestions
        print("\n🗑️  Clearing taxonomy suggestions...")
        deleted_suggestions = session.query(TaxonomySuggestions).delete()
        print(f"   ✅ Deleted {deleted_suggestions:,} taxonomy suggestions")
        
        # Commit
        session.commit()
        
        print("\n" + "="*80)
        print("✅ SUCCESS!")
        print("="*80)
        print(f"""
All nodes are now unclassified and will be re-classified when the taxonomy 
pipeline runs next.

To run the taxonomy pipeline:
  cd app/assistant/kg_core/taxonomy
  python pipeline.py

The improved classifiers will now classify all nodes from scratch.
        """)
        
    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        session.close()


if __name__ == '__main__':
    reclassify_all()

