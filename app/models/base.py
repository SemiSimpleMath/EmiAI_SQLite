# base.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import threading

# Module-level cache for engines and sessionmakers (singleton pattern)
# Keyed by database URI to support both test and dev databases
_engines = {}
_sessionmakers = {}
_engines_lock = threading.Lock()

# Database setup with SQLite
def get_database_uri():
    """Get database URI - using SQLite for this version"""
    # Use SQLite database in the project root
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'emi.db')
    # Convert to forward slashes for SQLite URI (required on all platforms)
    db_path = db_path.replace('\\', '/')
    return f'sqlite:///{db_path}'

def get_session(force_test_db=False):
    """
    Single source of truth for database sessions.
    Works for both Flask and standalone components.
    Always uses the correct database based on USE_TEST_DB environment variable.
    
    Uses a singleton engine pattern to reuse connection pools and prevent
    connection exhaustion.
    
    Thread Safety:
    - The engine is thread-safe and shared across all threads
    - The connection pool (QueuePool) is thread-safe
    - Each call creates a NEW session - sessions are NOT thread-safe
    - Each thread must use its own session instance
    
    Args:
        force_test_db (bool): If True, force use test database regardless of environment variable
    """
    # Force set test database if requested
    if force_test_db:
        os.environ['USE_TEST_DB'] = 'true'
        os.environ['TEST_DB_NAME'] = 'test_emidb'
    
    database_uri = get_database_uri()
    
    # Get or create engine for this database URI (singleton pattern)
    # Thread-safe: lock protects dictionary access during engine creation
    with _engines_lock:
        if database_uri not in _engines:
            # Create engine with connection pooling
            # pool_size: number of connections to maintain
            # max_overflow: additional connections that can be created on demand
            # pool_recycle: close connections after this many seconds (prevent stale connections)
            _engines[database_uri] = create_engine(
                database_uri,
                echo=False,
                pool_size=10,           # Maintain 10 connections in pool
                max_overflow=20,       # Allow up to 20 additional connections
                pool_recycle=3600,     # Recycle connections after 1 hour
                pool_pre_ping=True     # Verify connections before using
            )
            _sessionmakers[database_uri] = sessionmaker(bind=_engines[database_uri])
        
        # Get the sessionmaker (thread-safe to call from multiple threads)
        session_maker = _sessionmakers[database_uri]
    
    # Create a new session for this thread (sessions are NOT thread-safe)
    # Each thread gets its own session instance
    return session_maker()

# Legacy functions for backward compatibility (deprecated)
# These now use the singleton engine pattern
def get_current_engine():
    """Get the current engine based on environment configuration"""
    database_uri = get_database_uri()
    with _engines_lock:
        if database_uri not in _engines:
            _engines[database_uri] = create_engine(
                database_uri,
                echo=False,
                pool_size=10,
                max_overflow=20,
                pool_recycle=3600,
                pool_pre_ping=True
            )
            # IMPORTANT: Also create sessionmaker so get_session() works later
            _sessionmakers[database_uri] = sessionmaker(bind=_engines[database_uri])
        return _engines[database_uri]

def get_current_session():
    """Get a new session with the current database configuration"""
    return get_session()  # Use the unified function

# Base declarative base (this is safe to create at import time)
Base = declarative_base()

# Legacy functions for backward compatibility (deprecated)
# These now use the singleton engine pattern
def get_default_engine():
    """Get the default engine based on current environment configuration"""
    return get_current_engine()  # Reuse the singleton pattern

def get_default_session():
    """Get the default session based on current environment configuration"""
    return get_session()

# For backward compatibility, create these on demand
def get_legacy_engine():
    """Legacy function - use get_default_engine() instead"""
    return get_default_engine()

def get_legacy_session():
    """Legacy function - use get_default_session() instead"""
    return get_default_session()
