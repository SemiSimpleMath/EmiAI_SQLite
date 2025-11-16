# Graph Visualizer - Quick Reference

## 🚀 Getting Started

```bash
# Start Flask backend
python run_flask.py

# Start frontend (development)
cd app/graph_visualizer/frontend
npm start
```

**Access**: http://localhost:3000 or via Emi Dev Menu

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `?` | Show help |
| `Esc` | Close sidebar / deselect |
| `Ctrl+F` | Focus search |
| `Ctrl+E` | Export JSON |
| `R` | Refresh |
| `S` | Toggle stats |
| `L` | Toggle legend |
| `Space` | Pause/resume physics |

---

## 🔍 Common Tasks

### Search
```
Type in search box → Real-time filtering
Select node type from dropdown
Select edge type from dropdown
Click "Clear Filters" to reset
```

### View Details
```
Click node → Sidebar opens
Click edge → Edge details
Press Esc → Close sidebar
```

### Edit Node
```
Select node → Click "Edit"
Modify fields → Click "Save"
```

### Merge Nodes
```
Right-click node → "Merge with..."
Click target node
First node absorbs all connections
```

### Delete
```
Single: Select → "Delete" button
Bulk: POST /api/graph/nodes/bulk-delete
```

---

## 🎨 Visual Guide

### Node Colors
- **Blue**: Entity
- **Green**: Event
- **Orange**: Goal
- **Purple**: State
- **Pink**: Property
- **Cyan**: Concept

### Node Size
- **Larger** = Higher importance
- **Smaller** = Lower importance

### Edge Thickness
- **Thicker** = Higher confidence
- **Thinner** = Lower confidence

---

## 🔧 API Quick Reference

### GET Endpoints
```bash
# Get full graph
GET /api/graph

# Search
GET /api/graph/search?q=keyword&node_type=Entity

# Node details
GET /api/graph/node/<id>

# Edge details
GET /api/graph/edge/<id>

# Statistics
GET /api/graph/stats

# Types
GET /api/graph/node-types
GET /api/graph/edge-types
```

### PUT Endpoints
```bash
# Update node
PUT /api/graph/node/<id>
{
  "label": "New Label",
  "description": "Updated description",
  "aliases": ["alias1", "alias2"],
  "confidence": 0.95,
  "importance": 0.8
}

# Update edge
PUT /api/graph/edge/<id>
{
  "type": "NEW_TYPE",
  "confidence": 0.9,
  "sentence": "Updated sentence"
}
```

### DELETE Endpoints
```bash
# Delete node
DELETE /api/graph/node/<id>

# Delete edge
DELETE /api/graph/edge/<id>

# Bulk delete nodes
POST /api/graph/nodes/bulk-delete
{
  "node_type": "Entity",
  "preserve_edges": false
}

# Bulk delete edges
POST /api/graph/edges/bulk-delete
{
  "edge_type": "RELATIONSHIP"
}
```

### Special Operations
```bash
# Merge nodes
POST /api/graph/merge-nodes
{
  "node1_id": "uuid-1",  # Survivor
  "node2_id": "uuid-2"   # Deleted
}
```

---

## 🐛 Troubleshooting

### Problem: Graph won't load
**Solution**: Check Flask running on port 8000

### Problem: Orphaned edges warning
**Solution**: Run `python app/graph_visualizer/fix_orphaned_edges.py`

### Problem: Slow performance
**Solution**: 
- Disable auto-refresh
- Use node/edge filters
- Clear browser cache

### Problem: Nodes fly off screen
**Solution**: Adjust physics in `useGraphPhysics.ts`:
```typescript
graphRef.current?.d3Force('center').strength(0.5);
```

---

## 📊 Data Model Cheatsheet

### Node Fields
```typescript
id, label, node_type, category, aliases, description,
start_date, end_date, confidence, importance, source,
hash_tags, semantic_type, goal_status, attributes
```

### Edge Fields
```typescript
id, source_id, target_id, relationship_type,
relationship_descriptor, sentence, confidence,
importance, source, original_message_id,
sentence_id, attributes
```

---

## 🎯 Best Practices

1. **Use filters** for large graphs (>500 nodes)
2. **Merge duplicates** before they proliferate
3. **Export regularly** before bulk operations
4. **Verify orphaned edges** after mass deletes
5. **Use keyboard shortcuts** for efficiency
6. **Check stats panel** for graph health

---

## 📞 Need Help?

- **Full Docs**: `docs/graph_visualizer/GRAPH_VISUALIZER.md`
- **KG Docs**: `docs/knowledge_graph/README.md`
- **API Code**: `app/graph_visualizer/api.py`
- **Frontend Code**: `app/graph_visualizer/frontend/src/`

---

**Tip**: Press `?` in the visualizer for interactive help!
