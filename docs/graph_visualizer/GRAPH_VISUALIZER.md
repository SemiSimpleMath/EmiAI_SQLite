# Knowledge Graph Visualizer

## 📊 Overview

The Knowledge Graph Visualizer is a real-time interactive visualization system for Emi's Knowledge Graph. It provides a comprehensive interface to explore, search, filter, edit, and analyze the graph structure with live updates.

**Key Technologies:**
- **Backend**: Flask REST API with WebSocket support
- **Frontend**: React + TypeScript with force-directed graph visualization
- **Rendering**: react-force-graph-2d (D3-based physics simulation)
- **UI**: Tailwind CSS for responsive design
- **Database**: PostgreSQL with pgvector

---

## 🎯 Key Features

### 1. Interactive Visualization
- **Force-directed graph layout**: Physics-based node positioning for organic structure
- **Zoom & Pan**: Navigate large graphs with mouse/trackpad
- **Node click selection**: View detailed information about any node
- **Edge inspection**: Click edges to see relationship details
- **Highlighting**: Automatic highlighting of connected nodes/edges on hover
- **Context menu**: Right-click nodes for quick actions (merge, delete)

### 2. Search & Filtering
- **Text search**: Find nodes by label
- **Type filtering**: Filter nodes and edges by type
- **Combined filters**: Apply multiple filters simultaneously
- **Real-time results**: Graph updates as you type

### 3. Graph Analytics
- **Live statistics**: Node/edge counts, type distribution
- **Degree analysis**: Average node connections
- **Graph density**: Connectivity metrics
- **Type breakdown**: Visual charts of node/edge type distributions

### 4. Editing Capabilities
- **Node editing**: Update labels, descriptions, aliases, attributes
- **Edge editing**: Modify relationship types, confidence, importance
- **Node merging**: Combine duplicate nodes (preserves all edges)
- **Bulk operations**: Delete multiple nodes/edges by type
- **Undo-friendly**: All operations maintain referential integrity

### 5. Data Management
- **Export to JSON**: Download current graph state
- **Auto-refresh**: Optional periodic data reload
- **Real-time updates**: WebSocket notifications for graph changes
- **Orphaned edge detection**: Warnings for broken references

### 6. User Experience
- **Keyboard shortcuts**: Quick access to common actions (`?` for help)
- **Responsive design**: Works on desktop and tablets
- **Loading states**: Progress indicators with retry logic
- **Error recovery**: Graceful handling of network issues
- **Dark/Light themes**: (Inherits from main Emi UI)

---

## 🏗️ Architecture

### Backend Stack

```
app/graph_visualizer/
├── api.py              # REST API endpoints
├── websocket.py        # Real-time update handlers
└── frontend/           # React application
```

#### **API Endpoints** (`api.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/graph` | GET | Fetch all nodes and edges |
| `/api/graph/search` | GET | Search with filters |
| `/api/graph/node/<id>` | GET | Get node details + neighbors |
| `/api/graph/edge/<id>` | GET | Get edge details |
| `/api/graph/node/<id>` | PUT | Update node properties |
| `/api/graph/edge/<id>` | PUT | Update edge properties |
| `/api/graph/node/<id>` | DELETE | Delete node + connected edges |
| `/api/graph/edge/<id>` | DELETE | Delete edge |
| `/api/graph/nodes/bulk-delete` | POST | Delete multiple nodes |
| `/api/graph/edges/bulk-delete` | POST | Delete multiple edges |
| `/api/graph/merge-nodes` | POST | Merge two nodes |
| `/api/graph/node-types` | GET | List all node types |
| `/api/graph/edge-types` | GET | List all edge types |
| `/api/graph/stats` | GET | Graph statistics |

#### **Data Model Alignment**

The visualizer API maps directly to the KG database schema:

**Node Fields**:
```typescript
{
  id: UUID
  label: string
  node_type: string
  category: string (Person, Place, Organization, Thing)
  aliases: string[]
  description: text
  attributes: JSONB
  
  // Temporal
  start_date: datetime
  end_date: datetime
  start_date_confidence: string
  end_date_confidence: string
  valid_during: string
  
  // Metadata
  hash_tags: string[]
  semantic_type: string
  goal_status: string
  
  // Quality
  confidence: float (0.0-1.0)
  importance: float (0.0-1.0)
  source: string
  
  // Tracking
  original_message_id: string
  sentence_id: string
  created_at: datetime
  updated_at: datetime
}
```

**Edge Fields**:
```typescript
{
  id: UUID
  source_id: UUID (node)
  target_id: UUID (node)
  relationship_type: string
  relationship_descriptor: string
  attributes: JSONB
  sentence: text
  
  // Quality
  confidence: float (0.0-1.0)
  importance: float (0.0-1.0)
  source: string
  
  // Tracking
  original_message_id: string
  sentence_id: string
  original_message_timestamp: datetime
  created_at: datetime
  updated_at: datetime
}
```

### Frontend Stack

```
frontend/
├── src/
│   ├── App.tsx              # Main application orchestration
│   ├── components/          # UI components
│   │   ├── GraphCanvas.tsx      # Force-directed graph renderer
│   │   ├── NodeDetails.tsx      # Node information panel
│   │   ├── EdgeDetails.tsx      # Edge information panel
│   │   ├── SearchFilters.tsx    # Search and filter controls
│   │   ├── StatsPanel.tsx       # Graph statistics display
│   │   ├── Legend.tsx           # Node/edge type legend
│   │   ├── ContextMenu.tsx      # Right-click menu
│   │   ├── Sidebar/             # Collapsible sidebar
│   │   └── ...
│   ├── hooks/               # Custom React hooks
│   │   ├── useGraphData.ts      # Data fetching & caching
│   │   ├── useFilters.ts        # Search/filter state
│   │   ├── useHighlights.ts     # Selection highlighting
│   │   ├── useGraphPhysics.ts   # Physics simulation control
│   │   ├── useContextMenu.ts    # Right-click handling
│   │   ├── useAutoRefresh.ts    # Periodic refresh
│   │   └── useKeyboardShortcuts.ts
│   ├── api/                 # API client
│   │   ├── client.ts
│   │   └── graph.ts
│   ├── lib/                 # Utility functions
│   │   ├── colors.ts            # Node/edge coloring
│   │   ├── graphStats.ts        # Analytics calculations
│   │   ├── graphUtils.ts        # Helper functions
│   │   └── exportJson.ts        # Data export
│   └── types/
│       └── graph.ts             # TypeScript interfaces
```

#### **Key Components**

1. **`App.tsx`**: Main orchestrator
   - Manages global state (selected node/edge, filters, etc.)
   - Coordinates communication between components
   - Handles data fetching and updates

2. **`GraphCanvas.tsx`**: Visualization engine
   - Wraps `react-force-graph-2d`
   - Manages physics simulation (link force, charge, centering)
   - Handles node/edge rendering with custom colors and sizes
   - Implements click, hover, and drag interactions

3. **`NodeDetails.tsx` / `EdgeDetails.tsx`**: Information panels
   - Display full details for selected items
   - Support inline editing
   - Show incoming/outgoing connections
   - Provide delete functionality

4. **`SearchFilters.tsx`**: Filter controls
   - Text search input
   - Node/edge type dropdowns
   - Clear filters button

5. **`StatsPanel.tsx`**: Analytics dashboard
   - Total counts
   - Type distribution charts
   - Graph density metrics

#### **Custom Hooks**

1. **`useGraphData`**: Data management
   - Fetches graph data from API
   - Caches results
   - Provides search function
   - Handles loading/error states
   - Auto-retry on failure (exponential backoff)

2. **`useFilters`**: Filter state
   - Manages search query, node type, edge type
   - Provides update and clear functions
   - Syncs with URL params (optional)

3. **`useHighlights`**: Selection highlighting
   - Tracks highlighted nodes/edges
   - Automatic neighbor highlighting on hover
   - Clear function

4. **`useGraphPhysics`**: Physics control
   - Configures force simulation parameters
   - Detects when graph stabilizes
   - Provides reset function

5. **`useContextMenu`**: Right-click menu
   - Tracks menu position and target node
   - Provides open/close functions
   - Handles outside clicks

---

## 🚀 Setup & Usage

### Prerequisites
- Flask server running (port 8000)
- PostgreSQL database with KG data
- Node.js 16+ (for frontend development)

### Backend Setup

The visualizer API is already registered in `app/create_app.py`:

```python
from app.graph_visualizer.api import graph_api
app.register_blueprint(graph_api)
```

No additional backend setup required! The API is live when Flask starts.

### Frontend Setup

#### Development Mode

```bash
cd app/graph_visualizer/frontend
npm install
npm start
```

Frontend runs on `http://localhost:3000` with hot reload.

#### Production Build

```bash
npm run build
```

Build artifacts go to `frontend/build/`. Serve with Flask or nginx.

### Accessing the Visualizer

1. **Via Dev Menu**: Click "Dev Menu" button → "Graph Visualizer" tab
2. **Direct URL**: `http://localhost:5173` (if using Vite dev server)
3. **Standalone**: Run `python app/graph_visualizer/run_standalone.py`

---

## 🎨 Customization

### Node Colors

Edit `frontend/src/lib/colors.ts`:

```typescript
export const NODE_COLORS: { [key: string]: string } = {
  'Entity': '#3b82f6',      // Blue
  'Event': '#10b981',       // Green
  'Goal': '#f59e0b',        // Orange
  'State': '#8b5cf6',       // Purple
  'Property': '#ec4899',    // Pink
  'Concept': '#06b6d4',     // Cyan
};
```

### Node Sizing

Nodes are sized based on importance (if available):

```typescript
const getNodeSize = (node: Node) => {
  const baseSize = 5;
  const importanceBoost = (node.importance || 0.5) * 5;
  return baseSize + importanceBoost;
};
```

### Physics Parameters

Adjust in `frontend/src/hooks/useGraphPhysics.ts`:

```typescript
const configurePhysics = () => {
  graphRef.current?.d3Force('link').distance(50);
  graphRef.current?.d3Force('charge').strength(-300);
  graphRef.current?.d3Force('center').strength(0.1);
};
```

---

## 🔧 Common Operations

### Searching for a Node

1. Type in the search box (top left)
2. Graph filters in real-time
3. Click "Clear Filters" to reset

### Viewing Node Details

1. Click any node
2. Sidebar opens with full details
3. Click outside or press `Esc` to close

### Editing a Node

1. Select a node
2. Click "Edit" button
3. Modify fields
4. Click "Save" or "Cancel"

### Merging Duplicate Nodes

1. Right-click first node → "Merge with..."
2. Click second node
3. First node absorbs all edges
4. Second node is deleted

### Deleting Nodes

**Single node:**
1. Select node
2. Click "Delete" button
3. Confirm deletion

**Bulk delete by type:**
```bash
POST /api/graph/nodes/bulk-delete
{
  "node_type": "Entity",
  "preserve_edges": false
}
```

### Exporting Graph Data

1. Press `Ctrl+E` (or `Cmd+E` on Mac)
2. JSON file downloads with timestamp
3. Contains all nodes, edges, and metadata

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `?` | Show help modal |
| `Esc` | Close sidebar / deselect |
| `Ctrl+F` | Focus search box |
| `Ctrl+E` | Export graph data |
| `R` | Refresh graph |
| `S` | Toggle stats panel |
| `L` | Toggle legend |
| `Space` | Pause/resume physics |

---

## 🐛 Troubleshooting

### Graph Not Loading

**Symptoms**: Blank screen, "Loading..." forever

**Fixes**:
1. Check Flask server is running: `http://localhost:8000/api/graph`
2. Check browser console for errors (F12)
3. Verify CORS is enabled (should be automatic)
4. Check database connection in Flask logs

### Nodes Appear Then Disappear

**Cause**: Physics simulation pushing nodes off-screen

**Fix**: Increase center force strength:
```typescript
graphRef.current?.d3Force('center').strength(0.5);
```

### Orphaned Edges Warning

**Symptoms**: Console shows "Found X orphaned edges"

**Cause**: Edges reference deleted nodes

**Fix**: Run orphan cleanup script:
```bash
python app/graph_visualizer/fix_orphaned_edges.py
```

### Performance Issues (Large Graphs)

**Symptoms**: Slow rendering, lag on interactions

**Optimizations**:
1. Increase physics cooldown ticks (stabilizes faster)
2. Reduce number of rendered nodes (pagination)
3. Disable auto-refresh during exploration
4. Use WebGL renderer (not yet implemented)

### WebSocket Connection Errors

**Symptoms**: No real-time updates

**Note**: WebSocket support is optional. Visualizer works without it. If you need real-time updates, ensure SocketIO is configured in `app/create_app.py`.

---

## 📊 Performance Considerations

### Current Limits
- **Small graphs** (<100 nodes): Excellent performance
- **Medium graphs** (100-1000 nodes): Good performance
- **Large graphs** (1000-10000 nodes): Usable, may lag on slow devices
- **Very large graphs** (>10000 nodes): Consider pagination or clustering

### Optimization Strategies

1. **Lazy loading**: Only load visible subgraphs
2. **Clustering**: Group related nodes
3. **Pagination**: Load graph in chunks
4. **WebGL renderer**: Hardware acceleration (future enhancement)
5. **Caching**: Cache API responses client-side

---

## 🔐 Security Notes

- **Authentication**: Uses same auth as main Emi app (if configured)
- **CSRF Protection**: Flask-WTF handles this
- **SQL Injection**: All queries use SQLAlchemy ORM (safe)
- **XSS Prevention**: React sanitizes all rendered content
- **CORS**: Configured to allow `localhost:3000` in dev mode

**Production recommendations**:
- Enable HTTPS
- Restrict CORS to production domain
- Add rate limiting to API endpoints
- Implement audit logging for delete operations

---

## 🎯 Future Enhancements

### Planned Features
- [ ] **Time-travel**: View graph state at past timestamps
- [ ] **Diff view**: Compare graph changes between dates
- [ ] **Path finding**: Shortest path between two nodes
- [ ] **Community detection**: Identify node clusters
- [ ] **Graph templates**: Save/load custom views
- [ ] **Collaborative editing**: Multi-user graph editing
- [ ] **Version control**: Undo/redo with history
- [ ] **Mobile app**: React Native version

### Known Limitations
- No 3D visualization (2D only)
- No hierarchical layout (force-directed only)
- No edge bundling (can be messy with many edges)
- No animated transitions (instant updates)
- No offline mode (requires backend connection)

---

## 📚 Additional Resources

- **API Reference**: See `api.py` inline documentation
- **Component Docs**: TypeScript interfaces in source files
- **KG Schema**: `docs/knowledge_graph/KG_ARCHITECTURE.md`
- **React Force Graph Docs**: https://github.com/vasturiano/react-force-graph

---

## 🤝 Contributing

When adding features to the visualizer:

1. **Backend changes**: Update `api.py` and document new endpoints
2. **Frontend changes**: Add TypeScript types first, then components
3. **Breaking changes**: Update this documentation
4. **Testing**: Test with graphs of varying sizes (10, 100, 1000 nodes)
5. **Performance**: Profile with React DevTools before committing

---

## 📝 Version History

- **v1.0** (Initial): Basic force-directed graph with search/filter
- **v1.1** (Current): Added editing, merging, bulk operations, stats panel, keyboard shortcuts
- **v1.2** (Next): Time-travel, diff view, path finding

---

**Last Updated**: September 29, 2025
**Maintainer**: Emi AI Development Team
