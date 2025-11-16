import React from 'react';

interface HeaderBarProps {
  title?: string;
  onRefresh: () => void;
  onExport: () => void;
  onOpenSearch: () => void;
  autoRefresh: boolean;
  refreshInterval: number;
  onToggleAutoRefresh: () => void;
  onUpdateRefreshInterval: (interval: number) => void;
  loading: boolean;
  showStats: boolean;
  onToggleStats: () => void;
}

const HeaderBar: React.FC<HeaderBarProps> = ({
  title = "Knowledge Graph Visualizer",
  onRefresh,
  onExport,
  onOpenSearch,
  autoRefresh,
  refreshInterval,
  onToggleAutoRefresh,
  onUpdateRefreshInterval,
  loading,
  showStats,
  onToggleStats
}) => {
  return (
    <header className="bg-gray-800 border-b border-gray-700 px-4 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <h1 className="text-xl font-bold text-white">{title}</h1>
          {loading && (
            <div className="flex items-center space-x-2 text-xs text-white">
              <div className="loading-spinner rounded-full h-3 w-3 border-b-2 border-white"></div>
              <span>Loading...</span>
            </div>
          )}
        </div>
        
        <div className="flex items-center space-x-3">
          {/* Auto-refresh controls */}
          <div className="flex items-center space-x-2">
            <label className="flex items-center space-x-2 text-xs text-white">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={onToggleAutoRefresh}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span>Auto</span>
            </label>
            {autoRefresh && (
              <select
                value={refreshInterval}
                onChange={(e) => onUpdateRefreshInterval(Number(e.target.value))}
                className="text-xs border border-gray-600 rounded px-1 py-0.5 bg-gray-700 text-white"
              >
                <option value={10}>10s</option>
                <option value={30}>30s</option>
                <option value={60}>1m</option>
                <option value={300}>5m</option>
                <option value={600}>10m</option>
              </select>
            )}
          </div>
          
          {/* Action buttons */}
          <div className="flex items-center space-x-2">
            <button
              onClick={onOpenSearch}
              className="flex items-center space-x-1 px-3 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded"
            >
              <span>🔍</span>
              <span>Search</span>
            </button>
            <button
              onClick={onToggleStats}
              className={`px-3 py-1 text-xs font-medium rounded ${showStats ? 'bg-green-600 text-white hover:bg-green-700' : 'bg-gray-600 text-white hover:bg-gray-700'}`}
            >
              📊 Stats
            </button>
            <button
              onClick={onRefresh}
              disabled={loading}
              className="px-3 py-1 text-xs font-medium bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed rounded"
            >
              🔄
            </button>
            <button
              onClick={onExport}
              className="px-3 py-1 text-xs font-medium bg-gray-600 text-white hover:bg-gray-700 rounded"
            >
              📥
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default HeaderBar;
