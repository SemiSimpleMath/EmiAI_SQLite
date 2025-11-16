import React from 'react';
import { nodeColors } from '../lib/colors';

interface LegendProps {
  nodeTypes: string[];
}

const Legend: React.FC<LegendProps> = ({ nodeTypes }) => {
  // Define the essential node types we want to show
  const essentialTypes = ['Entity', 'Event', 'State', 'Goal', 'Property', 'Concept'];
  
  return (
    <div className="legend-overlay">
      <h3 className="text-sm font-medium text-gray-900 mb-3">Legend</h3>
      
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          {essentialTypes.map(type => (
            <div key={type} className="flex items-center space-x-1">
              <div 
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: nodeColors[type] || nodeColors.default }}
              ></div>
              <span className="text-xs text-gray-600">{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Legend;
