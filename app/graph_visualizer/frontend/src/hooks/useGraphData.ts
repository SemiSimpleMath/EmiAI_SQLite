import { useState, useCallback, useRef } from 'react';
import { GraphData, GraphStats } from '../types/graph';
import { fetchGraphData, searchGraph } from '../api/graph';
import { calculateStats } from '../lib/graphStats';

export const useGraphData = () => {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [graphStats, setGraphStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingMessage, setLoadingMessage] = useState('Loading graph data...');
  const [retryCount, setRetryCount] = useState(0);
  const retryCountRef = useRef(0);

  const refetch = useCallback(async () => {
    try {
      setLoading(true);
      setLoadingProgress(0);
      setLoadingMessage('Connecting to server...');
      
      // Simulate progress for better UX
      const progressInterval = setInterval(() => {
        setLoadingProgress(prev => {
          if (prev < 90) return prev + 10;
          return prev;
        });
      }, 100);
      
      setLoadingMessage('Loading graph data...');
      setLoadingProgress(20);
      
      const data = await fetchGraphData();
      setLoadingProgress(60);
      setLoadingMessage('Processing nodes and edges...');
      
      setGraphData(data);
      setLoadingProgress(80);
      setLoadingMessage('Calculating statistics...');
      
      setGraphStats(calculateStats(data));
      setError(null);
      setRetryCount(0);
      retryCountRef.current = 0;
      setLoadingProgress(100);
      setLoadingMessage('Complete!');
      
      clearInterval(progressInterval);
      
      // Clear loading message after a brief delay
      setTimeout(() => {
        setLoadingMessage('Loading graph data...');
        setLoadingProgress(0);
      }, 500);
      
    } catch (err) {
      console.error('Error fetching graph data:', err);
      setLoadingMessage('Error loading data');
      
      // Auto-retry logic (up to 3 attempts)
      if (retryCountRef.current < 3) {
        retryCountRef.current += 1;
        setRetryCount(retryCountRef.current);
        setLoadingMessage(`Retrying... (${retryCountRef.current}/3)`);
        setTimeout(() => {
          refetch();
        }, 2000 * retryCountRef.current); // Exponential backoff
      } else {
        setError('Failed to load graph data after multiple attempts');
        setRetryCount(0);
        retryCountRef.current = 0;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const search = useCallback(async (filters: {
    searchQuery?: string;
    nodeTypeFilter?: string;
    edgeTypeFilter?: string;
  }) => {
    try {
      setLoading(true);
      const data = await searchGraph(filters);
      setGraphData(data);
      setGraphStats(calculateStats(data));
      setError(null);
    } catch (err) {
      setError('Failed to search graph');
      console.error('Error searching graph:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const updateGraphData = useCallback((newData: GraphData) => {
    setGraphData(newData);
    setGraphStats(calculateStats(newData));
  }, []);

  return {
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
  };
};
