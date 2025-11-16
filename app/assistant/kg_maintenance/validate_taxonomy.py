"""
Taxonomy Validation Script

Validates taxonomy consistency, hierarchy, and semantic correctness.
Distinguishes between legitimate multi-faceted concepts and problematic duplicates.
"""

import sys
import re
from collections import defaultdict
from typing import List, Dict, Tuple
from sqlalchemy import func, text

from app.models.base import get_session
from app.assistant.kg_core.taxonomy_db import Taxonomy
from app.assistant.kg_core.knowledge_graph_utils import KnowledgeGraphUtils


class TaxonomyValidator:
    def __init__(self):
        self.session = get_session()
        self.kg_utils = KnowledgeGraphUtils(self.session)
        self.errors = []
        self.warnings = []
        self.info = []
    
    def run_all_validations(self):
        """Run complete validation suite."""
        print("🔍 Running Taxonomy Validation Suite...\n")
        
        results = {}
        
        print("1️⃣  Structural Integrity...")
        results['structural'] = self.validate_structure()
        
        print("\n2️⃣  Naming Conventions...")
        results['naming'] = self.validate_naming()
        
        print("\n3️⃣  Hierarchy Consistency...")
        results['hierarchy'] = self.validate_hierarchy()
        
        print("\n4️⃣  Embedding Coverage...")
        results['embeddings'] = self.validate_embeddings()
        
        print("\n5️⃣  Duplicate Analysis...")
        results['duplicates'] = self.analyze_duplicates()
        
        print("\n6️⃣  Multi-Faceted Concepts...")
        self.analyze_multi_faceted_concepts()
        
        self.print_summary(results)
        
        return all(results.values())
    
    def validate_structure(self):
        """Check database structural integrity."""
        passed = True
        
        # Check for orphaned nodes
        orphans = self.session.execute(text("""
            SELECT t1.id, t1.label, t1.parent_id
            FROM taxonomy t1
            LEFT JOIN taxonomy t2 ON t1.parent_id = t2.id
            WHERE t1.parent_id IS NOT NULL AND t2.id IS NULL
        """)).fetchall()
        
        if orphans:
            self.errors.append(f"Found {len(orphans)} orphaned nodes (parent_id points to non-existent node)")
            for orphan in orphans[:5]:
                self.errors.append(f"  - {orphan[1]} (parent_id={orphan[2]})")
            passed = False
        else:
            print("  ✅ No orphaned nodes")
        
        # Check root nodes
        roots = self.session.query(Taxonomy).filter(Taxonomy.parent_id == None).all()
        expected_roots = {"entity", "event", "state", "goal", "concept", "property"}
        actual_roots = {r.label for r in roots}
        
        if actual_roots == expected_roots:
            print(f"  ✅ All 6 root nodes present: {', '.join(sorted(actual_roots))}")
        else:
            missing = expected_roots - actual_roots
            extra = actual_roots - expected_roots
            if missing:
                self.errors.append(f"Missing root nodes: {missing}")
                passed = False
            if extra:
                self.warnings.append(f"Unexpected root nodes: {extra}")
        
        # Check for exact label duplicates (same label, same parent)
        duplicates = self.session.execute(text("""
            SELECT label, parent_id, COUNT(*) as count
            FROM taxonomy
            GROUP BY label, parent_id
            HAVING COUNT(*) > 1
        """)).fetchall()
        
        if duplicates:
            self.errors.append(f"Found {len(duplicates)} exact duplicates (same label + parent)")
            for dup in duplicates[:5]:
                self.errors.append(f"  - {dup[0]} under parent_id={dup[1]} ({dup[2]} times)")
            passed = False
        else:
            print("  ✅ No exact duplicates (same label + parent)")
        
        return passed
    
    def validate_naming(self):
        """Validate naming conventions."""
        passed = True
        
        all_taxonomy = self.session.query(Taxonomy).all()
        violations = []
        
        for tax in all_taxonomy:
            # Check lowercase
            if tax.label != tax.label.lower():
                violations.append(f"{tax.label} - Not lowercase")
            
            # Check no spaces
            if ' ' in tax.label:
                violations.append(f"{tax.label} - Contains spaces")
            
            # Check valid characters (alphanumeric + underscore)
            if not re.match(r'^[a-z0-9_]+$', tax.label):
                violations.append(f"{tax.label} - Invalid characters")
        
        if violations:
            self.errors.append(f"Found {len(violations)} naming convention violations:")
            for v in violations[:10]:
                self.errors.append(f"  - {v}")
            if len(violations) > 10:
                self.errors.append(f"  ... and {len(violations) - 10} more")
            passed = False
        else:
            print(f"  ✅ All {len(all_taxonomy)} labels follow lowercase_snake_case convention")
        
        return passed
    
    def validate_hierarchy(self):
        """Validate hierarchy structure."""
        passed = True
        
        # Check depth distribution
        depth_distribution = self.session.execute(text("""
            WITH RECURSIVE depth_calc AS (
                SELECT id, label, parent_id, 0 as depth
                FROM taxonomy WHERE parent_id IS NULL
                UNION ALL
                SELECT t.id, t.label, t.parent_id, dc.depth + 1
                FROM taxonomy t
                JOIN depth_calc dc ON t.parent_id = dc.id
            )
            SELECT depth, COUNT(*) as count
            FROM depth_calc
            GROUP BY depth
            ORDER BY depth
        """)).fetchall()
        
        print("  📊 Depth distribution:")
        for depth, count in depth_distribution:
            print(f"    Level {depth}: {count:,} nodes")
        
        # Check for very deep hierarchies (might indicate issues)
        max_depth = max(d[0] for d in depth_distribution) if depth_distribution else 0
        if max_depth > 10:
            self.warnings.append(f"Very deep hierarchy detected (max depth: {max_depth})")
        
        # Check for very unbalanced parents (too many children)
        child_counts = self.session.execute(text("""
            SELECT parent.label, COUNT(child.id) as num_children
            FROM taxonomy child
            JOIN taxonomy parent ON child.parent_id = parent.id
            GROUP BY parent.id, parent.label
            HAVING COUNT(child.id) > 1000
            ORDER BY num_children DESC
        """)).fetchall()
        
        if child_counts:
            self.warnings.append(f"Found {len(child_counts)} nodes with >1000 children:")
            for label, count in child_counts[:5]:
                self.warnings.append(f"  - {label}: {count:,} children")
        
        return passed
    
    def validate_embeddings(self):
        """Validate embedding coverage."""
        passed = True
        
        result = self.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(label_embedding) as with_embeddings,
                COUNT(*) - COUNT(label_embedding) as missing_embeddings
            FROM taxonomy
        """)).fetchone()
        
        total, with_embeddings, missing = result
        
        if missing > 0:
            self.errors.append(f"Missing embeddings: {missing}/{total} nodes")
            
            # Show examples
            missing_nodes = self.session.execute(text("""
                SELECT label FROM taxonomy 
                WHERE label_embedding IS NULL 
                LIMIT 5
            """)).fetchall()
            
            for node in missing_nodes:
                self.errors.append(f"  - {node[0]}")
            
            passed = False
        else:
            print(f"  ✅ All {total:,} nodes have embeddings")
        
        # Check embedding dimensions
        if with_embeddings > 0:
            sample_embedding = self.session.execute(text("""
                SELECT label_embedding FROM taxonomy 
                WHERE label_embedding IS NOT NULL 
                LIMIT 1
            """)).fetchone()
            
            if sample_embedding and sample_embedding[0]:
                dim = len(sample_embedding[0])
                if dim == 384:
                    print(f"  ✅ Embeddings are 384-dimensional (correct for all-MiniLM-L6-v2)")
                else:
                    self.errors.append(f"Incorrect embedding dimension: {dim} (expected 384)")
                    passed = False
        
        return passed
    
    def analyze_duplicates(self):
        """Analyze potential duplicates - distinguish legitimate from problematic."""
        passed = True
        
        # Find labels that appear multiple times (across different parents)
        duplicate_labels = self.session.execute(text("""
            SELECT label, COUNT(DISTINCT parent_id) as parent_count, 
                   array_agg(DISTINCT parent_id) as parent_ids
            FROM taxonomy
            GROUP BY label
            HAVING COUNT(DISTINCT parent_id) > 1
            ORDER BY COUNT(DISTINCT parent_id) DESC
        """)).fetchall()
        
        if not duplicate_labels:
            print("  ✅ No labels appear under multiple parents")
            return passed
        
        print(f"  📊 Found {len(duplicate_labels)} labels under multiple parents")
        print("     Analyzing for legitimacy...\n")
        
        # Get root type for each node to check if it's multi-faceted
        legitimate_multi_faceted = []
        suspicious_duplicates = []
        
        for label, parent_count, parent_ids in duplicate_labels[:20]:  # Analyze top 20
            nodes = self.session.query(Taxonomy).filter(Taxonomy.label == label).all()
            
            # Get root types
            root_types = set()
            for node in nodes:
                root = self._get_root_type(node)
                root_types.add(root)
            
            # If under different root types, it's likely legitimate multi-faceted
            if len(root_types) > 1:
                legitimate_multi_faceted.append({
                    "label": label,
                    "root_types": sorted(root_types),
                    "count": len(nodes)
                })
            else:
                # Same root type = suspicious duplicate
                suspicious_duplicates.append({
                    "label": label,
                    "root_type": list(root_types)[0],
                    "count": len(nodes),
                    "parent_labels": [self._get_parent_label(n.parent_id) for n in nodes]
                })
        
        # Report legitimate multi-faceted concepts
        if legitimate_multi_faceted:
            print(f"  ✅ Legitimate multi-faceted concepts: {len(legitimate_multi_faceted)}")
            self.info.append("\n  Examples of multi-faceted concepts (different aspects):")
            for item in legitimate_multi_faceted[:5]:
                roots_str = " + ".join(item['root_types'])
                self.info.append(f"    • {item['label']}: {roots_str}")
        
        # Report suspicious duplicates
        if suspicious_duplicates:
            print(f"  ⚠️  Suspicious duplicates (same root type): {len(suspicious_duplicates)}")
            self.warnings.append("\n  Suspicious duplicates to review:")
            for item in suspicious_duplicates[:5]:
                parents_str = ", ".join(item['parent_labels'])
                self.warnings.append(f"    • {item['label']} ({item['root_type']}): {parents_str}")
        
        return passed
    
    def analyze_multi_faceted_concepts(self):
        """Deep analysis of multi-faceted concepts."""
        print("  📊 Analyzing common multi-faceted patterns...\n")
        
        # Common concepts that should appear in multiple root types
        expected_multi_faceted = {
            "project": ["entity", "goal", "state"],
            "therapy": ["event", "state", "concept"],
            "meeting": ["event", "state"],
        }
        
        for concept, expected_roots in expected_multi_faceted.items():
            nodes = self.session.query(Taxonomy).filter(
                Taxonomy.label.contains(concept)
            ).all()
            
            if not nodes:
                continue
            
            actual_roots = set()
            for node in nodes:
                root = self._get_root_type(node)
                actual_roots.add(root)
            
            expected_set = set(expected_roots)
            found = expected_set & actual_roots
            missing = expected_set - actual_roots
            
            print(f"    {concept}:")
            print(f"      Found in: {', '.join(sorted(actual_roots))}")
            if missing:
                print(f"      Missing from: {', '.join(missing)}")
            print()
    
    def _get_root_type(self, node: Taxonomy) -> str:
        """Get the root type (entity/event/state/goal/concept/property) for a node."""
        current = node
        while current.parent_id is not None:
            parent = self.session.query(Taxonomy).filter(Taxonomy.id == current.parent_id).first()
            if not parent:
                break
            current = parent
        return current.label
    
    def _get_parent_label(self, parent_id: int) -> str:
        """Get label of parent node."""
        if not parent_id:
            return "ROOT"
        parent = self.session.query(Taxonomy).filter(Taxonomy.id == parent_id).first()
        return parent.label if parent else "UNKNOWN"
    
    def print_summary(self, results: Dict[str, bool]):
        """Print validation summary."""
        print("\n" + "="*70)
        print("VALIDATION SUMMARY")
        print("="*70)
        
        for category, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{category.upper():.<30} {status}")
        
        # Print errors
        if self.errors:
            print("\n" + "="*70)
            print("ERRORS (Must Fix)")
            print("="*70)
            for error in self.errors:
                print(error)
        
        # Print warnings
        if self.warnings:
            print("\n" + "="*70)
            print("WARNINGS (Review Recommended)")
            print("="*70)
            for warning in self.warnings:
                print(warning)
        
        # Print info
        if self.info:
            print("\n" + "="*70)
            print("INFORMATION")
            print("="*70)
            for info in self.info:
                print(info)
        
        # Final verdict
        print("\n" + "="*70)
        all_passed = all(results.values())
        if all_passed and not self.errors:
            print("🎉 ALL VALIDATIONS PASSED! Taxonomy is consistent and ready to use.")
        elif all_passed and self.warnings:
            print("✅ Core validations passed, but review warnings above.")
        else:
            print("⚠️  VALIDATION FAILED. Fix errors above before proceeding.")
        print("="*70)
        
        return all_passed


def main():
    validator = TaxonomyValidator()
    try:
        success = validator.run_all_validations()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        validator.session.close()


if __name__ == "__main__":
    main()

