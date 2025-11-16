import { apiClient } from './client';
import { GraphData, NodeDetailsData, Node, Edge } from '../types/graph';

// Fetch complete graph data
export const fetchGraphData = async (): Promise<GraphData> => {
  const response = await apiClient.get('/graph');
  const data = response.data;
  // Ensure links property exists for ForceGraph2D compatibility
  return {
    ...data,
    links: data.edges || data.links || []
  };
};

// Search graph with filters
export const searchGraph = async (filters: {
  searchQuery?: string;
  nodeTypeFilter?: string;
  edgeTypeFilter?: string;
}): Promise<GraphData> => {
  const params = new URLSearchParams();
  if (filters.searchQuery) params.append('q', filters.searchQuery);
  if (filters.nodeTypeFilter) params.append('node_type', filters.nodeTypeFilter);
  if (filters.edgeTypeFilter) params.append('edge_type', filters.edgeTypeFilter);
  
  const response = await apiClient.get(`/graph/search?${params.toString()}`);
  const data = response.data;
  // Ensure links property exists for ForceGraph2D compatibility
  return {
    ...data,
    links: data.edges || data.links || []
  };
};

// Fetch available node and edge types
export const fetchTypes = async (): Promise<{
  nodeTypes: string[];
  edgeTypes: string[];
  nodeClassifications: string[];
}> => {
  const [nodeTypesResponse, edgeTypesResponse] = await Promise.all([
    apiClient.get('/graph/node-types'),
    apiClient.get('/graph/edge-types')
  ]);
  
  const nodeTypes = nodeTypesResponse.data.map((nt: any) => nt.node_type);
  const edgeTypes = edgeTypesResponse.data.map((et: any) => et.relationship_type);
  const nodeClassifications = ['entity_node', 'property_node', 'event_node', 'goal_node', 'state_node'];
  
  return { nodeTypes, edgeTypes, nodeClassifications };
};

// Fetch detailed information about a specific node
export const fetchNodeDetails = async (nodeId: string): Promise<NodeDetailsData> => {
  const response = await apiClient.get(`/graph/node/${nodeId}`);
  return response.data;
};

// Delete a node
export const deleteNode = async (nodeId: string): Promise<void> => {
  await apiClient.delete(`/graph/node/${nodeId}`);
};

// Delete an edge
export const deleteEdge = async (edgeId: string): Promise<void> => {
  await apiClient.delete(`/graph/edge/${edgeId}`);
};

// Update a node
export const updateNode = async (nodeId: string, updates: Partial<Node>): Promise<Node> => {
  const response = await apiClient.put(`/graph/node/${nodeId}`, updates);
  return response.data;
};

// Update an edge
export const updateEdge = async (edgeId: string, updates: Partial<Edge>): Promise<Edge> => {
  const response = await apiClient.put(`/graph/edge/${edgeId}`, updates);
  return response.data;
};
