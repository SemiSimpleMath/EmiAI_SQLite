import React, { useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { GraphData, Node, Edge } from '../types/graph';
import { getNodeColorByClassification } from '../lib/colors';
import { getNodeSize as getNodeSizeUtil, getEdgeWidth as getEdgeWidthUtil, getEdgeColor as getEdgeColorUtil } from '../lib/graphUtils';
import Legend from './Legend';

interface GraphCanvasProps {
  graphData: GraphData | null;
  highlightedNodes: Set<string>;
  highlightedEdges: Set<string>;
  onNodeClick: (node: Node) => void;
  onEdgeClick: (edge: Edge) => void;
  onNodeRightClick: (node: Node, event: MouseEvent) => void;
  onBackgroundClick: () => void;
  graphRef: React.RefObject<any>;
  onEngineStop: () => void;
  nodeTypes: string[];
}

const GraphCanvas: React.FC<GraphCanvasProps> = ({
  graphData,
  highlightedNodes,
  highlightedEdges,
  onNodeClick,
  onEdgeClick,
  onNodeRightClick,
  onBackgroundClick,
  graphRef,
  onEngineStop,
  nodeTypes,
}) => {
  const getNodeColor = useCallback((node: Node): string => {
    if (highlightedNodes.has(node.id)) {
      return '#ff6b6b'; // Highlight color
    }
    return getNodeColorByClassification(node);
  }, [highlightedNodes]);

  const getNodeSize = useCallback((node: Node): number => {
    if (!graphData) return 4;
    return getNodeSizeUtil(node, graphData);
  }, [graphData]);

  const getEdgeWidth = useCallback((edge: Edge): number => {
    if (highlightedEdges.has(edge.id)) {
      return 3; // Highlighted edges are thicker
    }
    return getEdgeWidthUtil(edge);
  }, [highlightedEdges]);

  const getEdgeColor = useCallback((edge: Edge): string => {
    if (highlightedEdges.has(edge.id)) {
      return '#ff6b6b'; // Highlight color
    }
    return getEdgeColorUtil(edge);
  }, [highlightedEdges]);

  if (!graphData) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="text-gray-500 text-lg">No graph data available</div>
          <div className="text-gray-400 text-sm mt-2">Load data to visualize the graph</div>
        </div>
      </div>
    );
  }

  return (
    <div className="graph-visualization-container">
      <div className="force-graph-container">
        <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        linkSource="source_node"
        linkTarget="target_node"
        nodeLabel={(node: Node) => node.label}
        nodeColor={getNodeColor}
        nodeVal={getNodeSize}
        nodeCanvasObject={(node: Node, ctx: CanvasRenderingContext2D, globalScale: number) => {
          const label = node.label;
          const fontSize = Math.max(8, 12 / globalScale);
          ctx.font = `${fontSize}px Sans-Serif`;
          const textWidth = ctx.measureText(label).width;
          const bckgDimensions: [number, number] = [textWidth, fontSize].map(n => n + fontSize * 0.2) as [number, number];

          const x = node.x || 0;
          const y = node.y || 0;

          // Draw background
          ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
          ctx.fillRect(
            x - bckgDimensions[0] / 2,
            y - bckgDimensions[1] / 2,
            bckgDimensions[0],
            bckgDimensions[1]
          );

          // Draw text
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = getNodeColor(node);
          ctx.fillText(label, x, y);

          // Store dimensions for pointer area
          (node as any).__bckgDimensions = bckgDimensions;
        }}
        nodePointerAreaPaint={(node: Node, color: string, ctx: CanvasRenderingContext2D) => {
          ctx.fillStyle = color;
          const bckgDimensions = (node as any).__bckgDimensions;
          const x = node.x || 0;
          const y = node.y || 0;
          bckgDimensions && ctx.fillRect(x - bckgDimensions[0] / 2, y - bckgDimensions[1] / 2, bckgDimensions[0], bckgDimensions[1]);
        }}
        linkLabel={(edge: Edge) => `${edge.type}`}
        linkWidth={getEdgeWidth}
        linkColor={getEdgeColor}
        linkDirectionalArrowLength={0}
        linkDirectionalArrowRelPos={0}
        onNodeClick={onNodeClick}
        onLinkClick={onEdgeClick}
        onNodeRightClick={onNodeRightClick}
        onBackgroundClick={onBackgroundClick}
        onEngineStop={onEngineStop}
        cooldownTicks={100}
        d3AlphaDecay={0.0228}
        d3VelocityDecay={0.4}
        enableZoomInteraction={true}
        enablePanInteraction={true}
        enableNodeDrag={true}
        width={undefined}
        height={undefined}
      />
      
      {/* Legend overlay */}
      <Legend nodeTypes={nodeTypes} />
      </div>
    </div>
  );
};

export default GraphCanvas;
