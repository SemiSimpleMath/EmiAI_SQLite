# Graph Visualizer Documentation

Welcome to the Knowledge Graph Visualizer documentation!

## 📚 Documentation Index

### 1. **[GRAPH_VISUALIZER.md](./GRAPH_VISUALIZER.md)** - Complete Guide
   - **What**: Comprehensive documentation covering everything
   - **When to use**: First-time setup, in-depth understanding, troubleshooting
   - **Topics**:
     - Architecture & design
     - All features explained
     - API reference
     - Customization guide
     - Security considerations
     - Future roadmap

### 2. **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** - Cheat Sheet
   - **What**: Fast lookup for common tasks
   - **When to use**: Daily usage, quick API lookups, keyboard shortcuts
   - **Topics**:
     - Keyboard shortcuts
     - Common operations
     - API endpoints
     - Troubleshooting
     - Best practices

### 3. **[SCHEMA_INCONSISTENCIES_FIXED.md](./SCHEMA_INCONSISTENCIES_FIXED.md)** - Change Log
   - **What**: Record of schema mismatches found and fixed
   - **When to use**: Understanding recent changes, debugging schema issues
   - **Topics**:
     - Issues found during code review
     - Fixes applied
     - Verification checklist

---

## 🚀 Quick Start

### I want to...

**...run the visualizer**
```bash
# Backend already running with Flask
cd app/graph_visualizer/frontend
npm install
npm start
# Visit http://localhost:3000
```

**...understand the architecture**
→ Read [GRAPH_VISUALIZER.md - Architecture section](./GRAPH_VISUALIZER.md#-architecture)

**...use the API**
→ See [QUICK_REFERENCE.md - API section](./QUICK_REFERENCE.md#-api-quick-reference)

**...customize colors or layout**
→ Read [GRAPH_VISUALIZER.md - Customization section](./GRAPH_VISUALIZER.md#-customization)

**...troubleshoot an issue**
→ Check [QUICK_REFERENCE.md - Troubleshooting](./QUICK_REFERENCE.md#-troubleshooting)

**...understand the data model**
→ See [GRAPH_VISUALIZER.md - Data Model Alignment](./GRAPH_VISUALIZER.md#data-model-alignment)

---

## 🎯 Feature Overview

The Knowledge Graph Visualizer provides:

- **Interactive 2D force-directed graph** with zoom/pan
- **Search and filtering** by text, node type, edge type
- **Real-time statistics** and analytics
- **Node/edge editing** with full CRUD operations
- **Node merging** for duplicate resolution
- **Bulk operations** for mass updates
- **Export to JSON** for backups
- **Keyboard shortcuts** for power users
- **Responsive design** for desktop and tablet

---

## 🏗️ System Overview

```
┌─────────────────────────────────────────────────────┐
│                   Flask Backend                      │
│  ┌─────────────┐        ┌──────────────┐           │
│  │   api.py    │◄──────►│ PostgreSQL   │           │
│  │ (REST API)  │        │ + pgvector   │           │
│  └─────────────┘        └──────────────┘           │
│         │                                            │
│         │ JSON                                       │
│         ▼                                            │
│  ┌─────────────┐                                    │
│  │ websocket.py│ (optional real-time updates)       │
│  └─────────────┘                                    │
└─────────────────────────────────────────────────────┘
         │
         │ HTTP/WebSocket
         ▼
┌─────────────────────────────────────────────────────┐
│              React Frontend (TypeScript)             │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐│
│  │  App.tsx     │  │  hooks/     │  │ components/││
│  │ (Orchestrator)  │ (State)     │  │ (UI)       ││
│  └──────────────┘  └─────────────┘  └────────────┘│
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │      react-force-graph-2d (D3.js)            │  │
│  │      (Physics simulation & rendering)        │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 📊 Data Flow

```
User Action → React Component → API Call → Flask Route 
    → SQLAlchemy Query → PostgreSQL → Response → State Update 
    → Re-render → User sees result
```

**Example**: Editing a node
1. User clicks "Edit" button
2. `NodeDetails.tsx` shows edit form
3. User clicks "Save"
4. `updateNode()` API function called
5. `PUT /api/graph/node/<id>` hits Flask
6. `api.py` updates database via SQLAlchemy
7. Response returns updated node
8. React state updates
9. Graph re-renders with new data

---

## 🔍 File Structure

```
app/graph_visualizer/
├── api.py                      # Flask REST API (16 endpoints)
├── websocket.py                # WebSocket handlers (optional)
├── fix_orphaned_edges.py       # Maintenance script
├── run_standalone.py           # Standalone launcher
├── standalone_app.py           # Standalone Flask app
└── frontend/                   # React application
    ├── src/
    │   ├── App.tsx            # Main component
    │   ├── components/        # UI components (14 files)
    │   ├── hooks/             # Custom hooks (7 files)
    │   ├── api/               # API client (2 files)
    │   ├── lib/               # Utilities (4 files)
    │   └── types/             # TypeScript types
    ├── public/                # Static assets
    └── package.json           # Dependencies

docs/graph_visualizer/
├── README.md                   # This file
├── GRAPH_VISUALIZER.md        # Full documentation
├── QUICK_REFERENCE.md         # Cheat sheet
└── SCHEMA_INCONSISTENCIES_FIXED.md  # Change log
```

---

## 🎓 Learning Path

### Beginner
1. Read this README
2. Follow Quick Start above
3. Use [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) for common tasks

### Intermediate
1. Read [GRAPH_VISUALIZER.md](./GRAPH_VISUALIZER.md) Architecture section
2. Explore API endpoints with Postman/curl
3. Try customizing node colors

### Advanced
1. Read full [GRAPH_VISUALIZER.md](./GRAPH_VISUALIZER.md)
2. Understand custom hooks in `frontend/src/hooks/`
3. Modify physics parameters
4. Add new features

### Contributing
1. Read all documentation
2. Check `SCHEMA_INCONSISTENCIES_FIXED.md` for recent changes
3. Follow TypeScript patterns in existing components
4. Test with graphs of varying sizes (10, 100, 1000 nodes)

---

## 🧪 Testing

### Manual Testing Checklist
- [ ] Graph loads without errors
- [ ] Search filters nodes
- [ ] Node selection shows details
- [ ] Edge click shows edge info
- [ ] Edit node saves changes
- [ ] Delete node works
- [ ] Merge nodes works
- [ ] Export downloads JSON
- [ ] Stats panel shows correct data
- [ ] Keyboard shortcuts work
- [ ] Responsive on different screen sizes

### API Testing
```bash
# Get all data
curl http://localhost:8000/api/graph

# Search
curl "http://localhost:8000/api/graph/search?q=test&node_type=Entity"

# Get node
curl http://localhost:8000/api/graph/node/<UUID>

# Update node
curl -X PUT http://localhost:8000/api/graph/node/<UUID> \
  -H "Content-Type: application/json" \
  -d '{"label": "New Label"}'
```

---

## 🐛 Known Issues

1. **Large graphs (>1000 nodes)** may be slow on older devices
   - **Workaround**: Use filters to reduce visible nodes

2. **Physics simulation** sometimes pushes nodes off-screen
   - **Workaround**: Increase center force strength

3. **Orphaned edges** can occur after bulk deletes
   - **Fix**: Run `python app/graph_visualizer/fix_orphaned_edges.py`

See [QUICK_REFERENCE.md - Troubleshooting](./QUICK_REFERENCE.md#-troubleshooting) for more.

---

## 🔗 Related Documentation

- **Knowledge Graph Architecture**: `docs/knowledge_graph/KG_ARCHITECTURE.md`
- **KG Pipeline Details**: `docs/knowledge_graph/KG_PIPELINE_DETAILS.md`
- **Database Schema**: `app/assistant/kg_core/knowledge_graph_db.py`
- **Main App Config**: `app/configs/config.py`

---

## 📞 Support

- **Bug Reports**: Check existing issues, then create new one
- **Feature Requests**: Propose in team discussions
- **Questions**: Check this README first, then ask team

---

**Version**: 1.1  
**Last Updated**: September 29, 2025  
**Maintained By**: Emi AI Development Team
