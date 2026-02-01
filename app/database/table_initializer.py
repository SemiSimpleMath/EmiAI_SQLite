"""
Centralized table initialization by feature group
Each function imports only its related models and creates tables

Table Groups:
- Core: Always created (mandatory)
- Entity Cards: Always created (core feature)
- News: Always created (small overhead)
- Knowledge Graph: Only if enabled (requires ChromaDB)
"""
from app.models.base import Base, get_current_engine
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


def initialize_core_tables():
    """
    Create mandatory tables for core functionality
    Always runs on startup
    
    Tables (9):
    - unified_log, agent_activity_log, info_database
    - rag_database, event_repository, email_check_state
    - processed_entity_log, unified_items, recurring_event_rules
    """
    logger.info("Initializing core tables...")
    
    # Import core models (this registers them with Base.metadata)
    from app.assistant.database.db_handler import (
        UnifiedLog, AgentActivityLog, InfoDatabase, 
        RAGDatabase, EventRepository, EmailCheckState
    )
    from app.assistant.database.processed_entity_log import ProcessedEntityLog
    from app.assistant.unified_item_manager.unified_item import UnifiedItem
    from app.assistant.unified_item_manager.recurring_event_rules import RecurringEventRule
    
    # Create all core tables (idempotent - only creates if missing)
    engine = get_current_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("✅ Core tables initialized (9 tables)")


def initialize_music_tables():
    """
    Create music/DJ tables (core feature)
    Always runs on startup
    
    Tables (6):
    - played_songs
    - music_tracks_spotify
    - music_genre_stats
    - music_genre_weights
    - music_artist_weights
    - music_track_weights
    """
    logger.info("Initializing music tables...")
    
    # NOTE: These models use Flask-SQLAlchemy's metadata (db.Model), not Base.metadata.
    # Create them explicitly to avoid relying on incidental imports.
    from app.assistant.database.db_instance import db
    from app.models.played_songs import PlayedSong
    from app.models.music_tracks_spotify import SpotifyMusicTrack
    from app.models.music_genre_stats import MusicGenreStats
    from app.models.music_weights import MusicGenreWeight, MusicArtistWeight, MusicTrackWeight

    db.Model.metadata.create_all(
        db.engine,
        tables=[
            PlayedSong.__table__,
            SpotifyMusicTrack.__table__,
            MusicGenreStats.__table__,
            MusicGenreWeight.__table__,
            MusicArtistWeight.__table__,
            MusicTrackWeight.__table__,
        ],
        checkfirst=True,
    )
    logger.info("✅ Music tables initialized (6 tables)")


def initialize_entity_card_tables():
    """
    Create entity card tables (core feature)
    Always runs on startup
    
    Tables (5):
    - entity_cards, entity_card_usage, entity_card_index
    - entity_card_run_log, description_run_log
    """
    logger.info("Initializing entity card tables...")
    
    from app.assistant.entity_management.entity_cards import (
        EntityCard, EntityCardUsage, EntityCardIndex,
        EntityCardRunLog, DescriptionRunLog
    )
    
    engine = get_current_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("✅ Entity card tables initialized (5 tables)")


def initialize_news_tables():
    """
    Create News tables
    Always runs on startup (small overhead)
    
    Tables (5):
    - news_categories, news_labels, news_scores
    - news_articles, news_feedbacks
    """
    logger.info("Initializing news tables...")
    
    try:
        from app.assistant.news.news_schema import (
            NewsCategory, NewsLabel, NewsScore, 
            NewsArticle, NewsFeedback
        )
        
        engine = get_current_engine()
        Base.metadata.create_all(engine, checkfirst=True)
        logger.info("✅ News tables initialized (5 tables)")
    except ImportError as e:
        logger.warning(f"⚠️ News models not found, skipping news tables: {e}")


def initialize_kg_tables():
    """
    Create Knowledge Graph tables (optional feature)
    Only run when KG feature is enabled
    
    ⚠️ REQUIRES: ChromaDB installation
    
    Tables (13):
    KG Core:
    - kg_node_metadata, kg_edge_metadata, message_source_mapping
    
    Taxonomy:
    - taxonomy, node_taxonomy_links, taxonomy_suggestions
    - taxonomy_suggestions_review, node_taxonomy_review_queue
    
    Standardization:
    - label_canon, label_alias, edge_canon, edge_alias, review_queue
    """
    logger.info("Initializing Knowledge Graph tables...")
    
    # KG core tables
    from app.assistant.kg_core.knowledge_graph_db_sqlite import (
        Node, Edge, MessageSourceMapping
    )
    
    # Taxonomy tables
    from app.assistant.kg_core.taxonomy.models import (
        Taxonomy, NodeTaxonomyLink, TaxonomySuggestion,
        TaxonomySuggestions, NodeTaxonomyReviewQueue
    )
    
    # Standardization tables
    from app.assistant.kg_core.models_standardization import (
        LabelCanon, LabelAlias, EdgeCanon, EdgeAlias, ReviewQueue
    )
    
    engine = get_current_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("✅ Knowledge Graph tables initialized (13 tables)")


def initialize_kg_pipeline_tables():
    """
    Create KG Pipeline V2 tables (advanced/developer feature)
    Only run if using the KG processing pipeline
    
    ⚠️ NOTE: Most users don't need these - only for advanced KG processing
    
    Tables (10):
    - pipeline_batches, pipeline_chunks, pipeline_edges
    - stage_results, stage_completion
    - fact_extraction_results, parser_results, metadata_results
    - merge_results, taxonomy_results
    """
    logger.info("Initializing KG Pipeline V2 tables...")
    
    from app.assistant.kg_core.kg_pipeline_v2.database_schema import (
        PipelineBatch, PipelineChunk, PipelineEdge,
        StageResult, StageCompletion,
        FactExtractionResult, ParserResult, MetadataResult,
        MergeResult, TaxonomyResult
    )
    
    engine = get_current_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("✅ KG Pipeline V2 tables initialized (10 tables)")


def initialize_always_on_tables():
    """
    Initialize tables that are always created on startup
    
    Total: 20 tables
    - Core: 9 tables
    - Entity Cards: 5 tables
    - News: 5 tables
    - Music: 1 table
    """
    logger.info("🚀 Initializing always-on database tables...")
    
    initialize_core_tables()
    initialize_entity_card_tables()
    initialize_news_tables()
    initialize_music_tables()
    
    logger.info("✅ Always-on tables ready (20 tables)")


def initialize_optional_tables():
    """
    Initialize tables for optional features based on settings
    
    Checks user settings to determine which optional tables to create:
    - Knowledge Graph (requires ChromaDB): 13 tables
    """
    from app.assistant.user_settings_manager.user_settings import can_run_feature
    
    logger.info("Checking optional feature tables...")
    
    # Knowledge Graph tables (requires ChromaDB)
    if can_run_feature('kg') or can_run_feature('taxonomy'):
        try:
            initialize_kg_tables()
        except ImportError as e:
            logger.error(f"❌ Failed to initialize KG tables (ChromaDB not installed?): {e}")
            logger.info("💡 To enable KG: pip install chromadb")
    else:
        logger.info("⏸️ KG/Taxonomy tables skipped (feature disabled in settings)")


def initialize_all_tables():
    """
    Initialize ALL tables
    - Always-on tables (19)
    - Optional tables based on settings (0-13)
    
    This is the main entry point called from create_app()
    """
    logger.info("=" * 60)
    logger.info("DATABASE INITIALIZATION")
    logger.info("=" * 60)
    
    # Always create these
    initialize_always_on_tables()
    
    # Optional based on settings
    initialize_optional_tables()
    
    logger.info("=" * 60)
    logger.info("✅ Database initialization complete!")
    logger.info("=" * 60)


def check_missing_tables():
    """
    Diagnostic: Check which tables exist vs which should exist
    
    Returns:
        dict: {
            'existing': list of existing table names,
            'expected': list of expected table names,
            'missing': list of missing table names
        }
    """
    from sqlalchemy import inspect
    engine = get_current_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    
    # Import all models to get expected tables
    initialize_always_on_tables()  # This registers always-on models with Base
    
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables
    extra_tables = existing_tables - expected_tables
    
    return {
        'existing': sorted(list(existing_tables)),
        'expected': sorted(list(expected_tables)),
        'missing': sorted(list(missing_tables)),
        'extra': sorted(list(extra_tables))
    }

