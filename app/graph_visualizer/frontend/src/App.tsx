import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './App.css';

// Components
import HeaderBar from './components/HeaderBar';
import SearchFilters from './components/SearchFilters';
import { SearchModal } from './components/SearchModal';
import StatsPanel from './components/StatsPanel';
import GraphCanvas from './components/GraphCanvas';
import Sidebar from './components/Sidebar/Sidebar';
import ContextMenu from './components/ContextMenu';
import KeyboardHelpModal from './components/KeyboardHelpModal';
import LoadError from './components/LoadError';
import LoadingScreen from './components/LoadingScreen';

// Hooks
import { useGraphData } from './hooks/useGraphData';
import { useFilters } from './hooks/useFilters';
import { useHighlights } from './hooks/useHighlights';
import { useAutoRefresh } from './hooks/useAutoRefresh';
import { useContextMenu } from './hooks/useContextMenu';
import { useGraphPhysics } from './hooks/useGraphPhysics';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';

// API and utilities
import { fetchTypes, fetchNodeDetails, deleteNode, deleteEdge, updateNode, updateEdge } from './api/graph';
import { exportGraphData } from './lib/exportJson';
import { getNodeLabelById, getNodeId } from './lib/graphUtils';
import { passesTaxonomyFilters } from './lib/taxonomyFilter';

// Types
import { Node, Edge, NodeDetailsData } from './types/graph';

const App: React.FC = () => {
  // State
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [nodeDetails, setNodeDetails] = useState<NodeDetailsData | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [showStats, setShowStats] = useState(true);
  const [nodeTypes, setNodeTypes] = useState<string[]>([]);
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);

  // Custom hooks
  const {
    graphData,
    graphStats,
    loading,
    error,
    loadingProgress,
    loadingMessage,
    retryCount,
    refetch,
    search,
    updateGraphData
  } = useGraphData();

  const {
    searchQuery,
    nodeTypeFilter,
    edgeTypeFilter,
    taxonomyKeyword,
    taxonomyPath,
    updateSearchQuery,
    updateNodeTypeFilter,
    updateEdgeTypeFilter,
    updateFilters,
    clearFilters,
    getFilters
  } = useFilters();

  const {
    highlightedNodes,
    highlightedEdges,
    highlightNodes,
    highlightEdges,
    clearHighlights
  } = useHighlights();

  const { autoRefresh, refreshInterval, toggleAutoRefresh, updateRefreshInterval } = useAutoRefresh(refetch);

  const { contextMenu, openContextMenu, closeContextMenu } = useContextMenu();

  const { physicsConfigured, graphRef, configurePhysics, onEngineStop } = useGraphPhysics();

  // Fetch types and initial graph data on mount
  useEffect(() => {
    const loadTypes = async () => {
      try {
        const { nodeTypes: types, edgeTypes: eTypes } = await fetchTypes();
        setNodeTypes(types);
        setEdgeTypes(eTypes);
    } catch (err) {
      console.error('Error fetching types:', err);
        // Set default values if types fail to load
        setNodeTypes([]);
        setEdgeTypes([]);
      }
    };
    
    // Load both types and graph data in parallel
    loadTypes();
    refetch();
  }, [refetch]);

  // Configure physics when graph data changes
  useEffect(() => {
    if (graphData && !physicsConfigured) {
      configurePhysics();
    }
  }, [graphData, physicsConfigured, configurePhysics]);

  // Event handlers
  const handleNodeClick = useCallback(async (node: Node) => {
    setSelectedNode(node);
    setSelectedEdge(null);
    setSidebarOpen(true);
    clearHighlights();
    
    // Fetch detailed node information including edges
    try {
      const details = await fetchNodeDetails(node.id);
      console.log('🔍 Fetched node details:', details);
      console.log('🔍 Incoming edges:', details.incoming_edges?.length || 0);
      console.log('🔍 Outgoing edges:', details.outgoing_edges?.length || 0);
      setNodeDetails(details);
    } catch (error) {
      console.error('Error fetching node details:', error);
      setNodeDetails(null);
    }
  }, [clearHighlights]);

  const handleEdgeClick = useCallback((edge: Edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
    setNodeDetails(null);
    setSidebarOpen(true);
    
    // Highlight connected nodes
    if (graphData) {
      const sourceId = getNodeId(edge.source_node);
      const targetId = getNodeId(edge.target_node);
      highlightNodes([sourceId, targetId]);
      highlightEdges([edge.id]);
    }
  }, [graphData, highlightNodes, highlightEdges]);

  const handleNodeRightClick = useCallback((node: Node, event: MouseEvent) => {
    event.preventDefault();
    openContextMenu(event.clientX, event.clientY, { id: node.id, label: node.label });
  }, [openContextMenu]);

  const handleBackgroundClick = useCallback(() => {
        setSelectedNode(null);
        setSelectedEdge(null);
        setNodeDetails(null);
    setSidebarOpen(false);
        clearHighlights();
  }, [clearHighlights]);

  const handleSearch = useCallback(() => {
    search(getFilters());
  }, [search, getFilters]);

  const handleExport = useCallback(() => {
    if (graphData) {
      exportGraphData(graphData, getFilters());
    }
  }, [graphData, getFilters]);

  const handleNodeSave = useCallback(async (updatedNode: Partial<Node>) => {
    if (selectedNode) {
      try {
        await updateNode(selectedNode.id, updatedNode);
        // Update local data
        if (graphData) {
          const updatedNodes = graphData.nodes.map(node => 
            node.id === selectedNode.id ? { ...node, ...updatedNode } : node
          );
          updateGraphData({ ...graphData, nodes: updatedNodes, links: graphData.edges });
        }
        setSelectedNode({ ...selectedNode, ...updatedNode });
      } catch (err) {
        console.error('Error updating node:', err);
      }
    }
  }, [selectedNode, graphData, updateGraphData]);

  const handleNodeDelete = useCallback(async (nodeId: string) => {
    try {
      await deleteNode(nodeId);

        // Update local data
        if (graphData) {
          const updatedNodes = graphData.nodes.filter(node => node.id !== nodeId);
          const updatedEdges = graphData.edges.filter(edge => {
            const sourceId = getNodeId(edge.source_node);
            const targetId = getNodeId(edge.target_node);
            return sourceId !== nodeId && targetId !== nodeId;
          });
          updateGraphData({ ...graphData, nodes: updatedNodes, edges: updatedEdges, links: updatedEdges });
        }

        setSidebarOpen(false);
        setSelectedNode(null);
        setSelectedEdge(null);
        setNodeDetails(null);
        clearHighlights();
    } catch (err) {
      console.error('Error deleting node:', err);
    }
  }, [graphData, updateGraphData, clearHighlights]);

  const handleEdgeSave = useCallback(async (updatedEdge: Partial<Edge>) => {
    if (selectedEdge) {
      try {
        console.log('Saving edge with data:', updatedEdge);
        const result = await updateEdge(selectedEdge.id, updatedEdge);
        console.log('Edge update result:', result);
        
        // Update local data
        if (graphData) {
          const updatedEdges = graphData.edges.map(edge => 
            edge.id === selectedEdge.id ? { ...edge, ...updatedEdge } : edge
          );
          updateGraphData({ ...graphData, edges: updatedEdges, links: updatedEdges });
        }
        setSelectedEdge({ ...selectedEdge, ...updatedEdge });
      } catch (err) {
        console.error('Error updating edge:', err);
      }
    }
  }, [selectedEdge, graphData, updateGraphData]);

  const handleEdgeDelete = useCallback(async (edgeId: string) => {
    try {
      await deleteEdge(edgeId);

        // Update local data
        if (graphData) {
          const updatedEdges = graphData.edges.filter(edge => edge.id !== edgeId);
          updateGraphData({ ...graphData, edges: updatedEdges, links: updatedEdges });
        }

      setSidebarOpen(false);
      setSelectedNode(null);
      setSelectedEdge(null);
      setNodeDetails(null);
      clearHighlights();
    } catch (err) {
      console.error('Error deleting edge:', err);
    }
  }, [graphData, updateGraphData, clearHighlights]);

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onRefresh: refetch,
    onExport: handleExport,
    onClearHighlights: clearHighlights,
    onToggleAutoRefresh: toggleAutoRefresh,
    onSearch: handleSearch,
    onCloseSidebar: () => setSidebarOpen(false)
  });

  // Filtered graph data
  const filteredGraphData = useMemo(() => {
    if (!graphData) return null;
    
    let filteredNodes = graphData.nodes;
    let filteredEdges = graphData.edges;
    
    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filteredNodes = filteredNodes.filter(node => 
        node.label.toLowerCase().includes(query) ||
        (node.description && node.description.toLowerCase().includes(query)) ||
        (node.aliases && node.aliases.some(alias => alias.toLowerCase().includes(query)))
      );
    }
    
    // Apply type filters
    if (nodeTypeFilter) {
      filteredNodes = filteredNodes.filter(node => node.type === nodeTypeFilter);
    }

    // Apply taxonomy filters
    if (taxonomyKeyword || taxonomyPath) {
      filteredNodes = filteredNodes.filter(node => 
        passesTaxonomyFilters(node, taxonomyKeyword, taxonomyPath)
      );
    }
    
    if (edgeTypeFilter) {
      filteredEdges = filteredEdges.filter(edge => edge.type === edgeTypeFilter);
    }

    // Filter edges to only include those connecting visible nodes
    const visibleNodeIds = new Set(filteredNodes.map(node => node.id));
    filteredEdges = filteredEdges.filter(edge => {
      const sourceId = getNodeId(edge.source_node);
      const targetId = getNodeId(edge.target_node);
      return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId);
    });

    return {
      nodes: filteredNodes,
      edges: filteredEdges,
      links: filteredEdges, // ForceGraph2D expects 'links' property
      timestamp: graphData.timestamp
    };
  }, [graphData, searchQuery, nodeTypeFilter, edgeTypeFilter, taxonomyKeyword, taxonomyPath]);

  // Calculate filtered stats
  const filteredStats = useMemo(() => {
    if (!filteredGraphData) return null;
    
    const { nodes, edges } = filteredGraphData;
    
    // Calculate node type distribution
    const nodeTypes: { [key: string]: number } = {};
    nodes.forEach(node => {
      nodeTypes[node.type] = (nodeTypes[node.type] || 0) + 1;
    });
    
    // Calculate edge type distribution
    const edgeTypes: { [key: string]: number } = {};
    edges.forEach(edge => {
      edgeTypes[edge.type] = (edgeTypes[edge.type] || 0) + 1;
    });
    
    // Calculate average degree
    const totalConnections = edges.length * 2; // Each edge connects 2 nodes
    const avgDegree = nodes.length > 0 ? totalConnections / nodes.length : 0;
    
    // Calculate density (for undirected graph: 2E / (V * (V-1)))
    const maxPossibleEdges = nodes.length > 1 ? (nodes.length * (nodes.length - 1)) / 2 : 0;
    const density = maxPossibleEdges > 0 ? edges.length / maxPossibleEdges : 0;
    
    return {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      nodeTypes,
      edgeTypes,
      avgNodeDegree: avgDegree,
      density
    };
  }, [filteredGraphData]);

    return (
    <div className="h-screen flex flex-col bg-gray-100">
      {/* Header */}
      <HeaderBar
        onRefresh={refetch}
        onExport={handleExport}
        onOpenSearch={() => setShowSearchModal(true)}
        autoRefresh={autoRefresh}
        refreshInterval={refreshInterval}
        onToggleAutoRefresh={toggleAutoRefresh}
        onUpdateRefreshInterval={updateRefreshInterval}
        loading={loading}
        showStats={showStats}
        onToggleStats={() => setShowStats(!showStats)}
      />

      {/* Search Modal */}
      <SearchModal
        isOpen={showSearchModal}
        onClose={() => setShowSearchModal(false)}
        filters={getFilters()}
        onFilterChange={updateFilters}
        onClearFilters={clearFilters}
      />

      {/* Search and Filters */}
      <SearchFilters
        filters={getFilters()}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onUpdateSearchQuery={updateSearchQuery}
        onUpdateNodeTypeFilter={updateNodeTypeFilter}
        onUpdateEdgeTypeFilter={updateEdgeTypeFilter}
        onSearch={handleSearch}
        onClearFilters={clearFilters}
        loading={loading}
      />

      {/* Stats Panel */}
      {showStats && (
        <div className="space-y-2">
          <StatsPanel stats={filteredStats} loading={loading} isFiltered={!!(searchQuery || nodeTypeFilter || edgeTypeFilter || taxonomyKeyword || taxonomyPath)} />
          {(searchQuery || nodeTypeFilter || edgeTypeFilter || taxonomyKeyword || taxonomyPath) && (
            <div className="text-xs text-gray-500 ml-2">
              Total: {graphStats?.totalNodes || 0} nodes, {graphStats?.totalEdges || 0} edges
            </div>
          )}
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex">
        {/* Graph Canvas */}
        <GraphCanvas
          graphData={filteredGraphData}
          highlightedNodes={highlightedNodes}
          highlightedEdges={highlightedEdges}
               onNodeClick={handleNodeClick}
          onEdgeClick={handleEdgeClick}
               onNodeRightClick={handleNodeRightClick}
          onBackgroundClick={handleBackgroundClick}
          graphRef={graphRef}
          onEngineStop={onEngineStop}
          nodeTypes={nodeTypes}
        />

        {/* Sidebar */}
        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          nodeDetails={nodeDetails}
          onNodeSave={handleNodeSave}
          onNodeDelete={handleNodeDelete}
          onEdgeSave={handleEdgeSave}
          onEdgeDelete={handleEdgeDelete}
          getNodeLabelById={getNodeLabelById}
          getNodeId={getNodeId}
        />
      </div>

      {/* Context Menu */}
      <ContextMenu
        contextMenu={contextMenu}
        onClose={closeContextMenu}
        onViewNode={(nodeId) => {
          const node = graphData?.nodes.find(n => n.id === nodeId);
          if (node) {
            handleNodeClick(node);
          }
        }}
        onDeleteNode={handleNodeDelete}
      />

      {/* Keyboard Help Modal */}
      <KeyboardHelpModal
        isOpen={showHelpModal}
        onClose={() => setShowHelpModal(false)}
      />

      {/* Loading Screen */}
      {loading && (
        <LoadingScreen
          progress={loadingProgress}
          message={loadingMessage}
        />
      )}

      {/* Error Display */}
      {error && (
        <LoadError
          error={error}
          retryCount={retryCount}
          onRetry={refetch}
        />
      )}
    </div>
  );
};

export default App; 
