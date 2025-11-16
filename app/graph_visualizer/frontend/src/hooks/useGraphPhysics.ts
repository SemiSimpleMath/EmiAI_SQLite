import { useState, useRef, useCallback } from 'react';
import * as d3 from 'd3';

export const useGraphPhysics = () => {
  const [physicsConfigured, setPhysicsConfigured] = useState(false);
  const [graphStable, setGraphStable] = useState(false);
  const graphRef = useRef<any>(null);

  const configurePhysics = useCallback(() => {
    if (graphRef.current && !physicsConfigured) {
      console.log('🔧 Configuring graph physics...');
      
      // Configure force simulation
      graphRef.current.d3Force('link')
        .distance(100)
        .strength(0.1);
      
      graphRef.current.d3Force('charge')
        .strength(-300)
        .distanceMax(400);
      
      graphRef.current.d3Force('center')
        .strength(0.1);
      
      // Add collision force to prevent node overlap
      graphRef.current.d3Force('collision', d3.forceCollide().radius(20));
      
      setPhysicsConfigured(true);
      console.log('✅ Physics configured');
    }
  }, [physicsConfigured]);

  const onEngineStop = useCallback(() => {
    console.log('🛑 Graph engine stopped');
    setGraphStable(true);
  }, []);

  const resetPhysics = useCallback(() => {
    setPhysicsConfigured(false);
    setGraphStable(false);
  }, []);

  return {
    physicsConfigured,
    graphStable,
    graphRef,
    configurePhysics,
    onEngineStop,
    resetPhysics
  };
};
