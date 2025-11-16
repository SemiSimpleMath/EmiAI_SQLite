"""Show taxonomy structure summary"""
import sqlite3

conn = sqlite3.connect('emi.db')

print("=" * 70)
print("TAXONOMY SUMMARY")
print("=" * 70)

# Root categories with their hierarchies
cursor = conn.execute("""
    SELECT id, label
    FROM taxonomy 
    WHERE parent_id IS NULL 
    ORDER BY label
""")

root_categories = cursor.fetchall()

for root_id, root_label in root_categories:
    # Count direct children
    cursor = conn.execute("""
        SELECT COUNT(*) FROM taxonomy WHERE parent_id = ?
    """, (root_id,))
    direct_children = cursor.fetchone()[0]
    
    # Count all descendants (recursive)
    cursor = conn.execute("""
        WITH RECURSIVE descendants AS (
            SELECT id FROM taxonomy WHERE parent_id = ?
            UNION ALL
            SELECT t.id FROM taxonomy t
            INNER JOIN descendants d ON t.parent_id = d.id
        )
        SELECT COUNT(*) FROM descendants
    """, (root_id,))
    total_descendants = cursor.fetchone()[0]
    
    # Count nodes classified under this taxonomy
    cursor = conn.execute("""
        SELECT COUNT(*) FROM node_taxonomy_links WHERE taxonomy_id = ?
    """, (root_id,))
    direct_nodes = cursor.fetchone()[0]
    
    # Count all nodes in this branch
    cursor = conn.execute("""
        WITH RECURSIVE descendants AS (
            SELECT id FROM taxonomy WHERE id = ?
            UNION ALL
            SELECT t.id FROM taxonomy t
            INNER JOIN descendants d ON t.parent_id = d.id
        )
        SELECT COUNT(DISTINCT ntl.node_id)
        FROM node_taxonomy_links ntl
        INNER JOIN descendants d ON ntl.taxonomy_id = d.id
    """, (root_id,))
    total_nodes = cursor.fetchone()[0]
    
    print(f"\n[{root_id}] {root_label.upper()}")
    print(f"   Direct children:     {direct_children:4}")
    print(f"   Total descendants:   {total_descendants:4}")
    print(f"   Direct nodes:        {direct_nodes:4}")
    print(f"   Total nodes:         {total_nodes:4}")
    
    # Show top 5 children
    cursor = conn.execute("""
        SELECT label, 
               (SELECT COUNT(*) FROM taxonomy t2 WHERE t2.parent_id = taxonomy.id) as child_count,
               (SELECT COUNT(*) FROM node_taxonomy_links WHERE taxonomy_id = taxonomy.id) as node_count
        FROM taxonomy 
        WHERE parent_id = ?
        ORDER BY node_count DESC, label
        LIMIT 5
    """, (root_id,))
    
    children = cursor.fetchall()
    if children:
        print(f"   Top children:")
        for child_label, child_count, node_count in children:
            print(f"      - {child_label:30} ({child_count:2} children, {node_count:3} nodes)")

# Overall stats
print("\n" + "=" * 70)
print("OVERALL STATISTICS:")
print("=" * 70)

cursor = conn.execute("SELECT COUNT(*) FROM taxonomy")
total_taxonomy = cursor.fetchone()[0]

cursor = conn.execute("SELECT COUNT(*) FROM node_taxonomy_links")
total_links = cursor.fetchone()[0]

cursor = conn.execute("SELECT COUNT(DISTINCT node_id) FROM node_taxonomy_links")
unique_nodes = cursor.fetchone()[0]

cursor = conn.execute("SELECT COUNT(DISTINCT taxonomy_id) FROM node_taxonomy_links")
used_taxonomy = cursor.fetchone()[0]

print(f"   Total taxonomy entries:        {total_taxonomy:,}")
print(f"   Taxonomy entries with nodes:   {used_taxonomy:,}")
print(f"   Total classification links:    {total_links:,}")
print(f"   Unique nodes classified:       {unique_nodes:,}")
print(f"   Avg classifications per node:  {total_links/unique_nodes:.2f}")

conn.close()

print("\n" + "=" * 70)




