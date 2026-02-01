#!/usr/bin/env python3
"""
Check Pipeline V2 Database Results

Check what data was written to the database after running stages.
"""

import logging
from app.models.base import get_session
from app.assistant.kg_core.kg_pipeline_v2.database_schema import PipelineBatch, PipelineChunk, StageResult, StageCompletion

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_database_results():
    """Check what data was written to the database"""
    session = get_session()
    try:
        print("Checking Pipeline V2 Database Results")
        print("=" * 50)
        
        # Check batches
        batches = session.query(PipelineBatch).all()
        print(f'Batches: {len(batches)}')
        for batch in batches:
            print(f'   - ID: {batch.id}, Name: {batch.batch_name}, Status: {batch.status}')
        
        # Check chunks
        chunks = session.query(PipelineChunk).all()
        print(f'Chunks: {len(chunks)}')
        for chunk in chunks:
            print(f'   - ID: {chunk.id}, Label: {chunk.label}, Type: {chunk.node_type}')
        
        # Check stage results
        results = session.query(StageResult).all()
        print(f'Stage Results: {len(results)}')
        for result in results:
            print(f'   - Chunk ID: {result.chunk_id[:8]}..., Stage: {result.stage_name}')
            if result.stage_name == 'conversation_boundary':
                print(f'     Data keys: {list(result.result_data.keys()) if result.result_data else "None"}')
                if result.result_data and 'conversation_chunks' in result.result_data:
                    chunks = result.result_data['conversation_chunks']
                    print(f'     Conversation chunks: {len(chunks)}')
                    if chunks:
                        print(f'     First chunk keys: {list(chunks[0].keys()) if chunks[0] else "None"}')
        
        # Check stage completions (summary)
        print(f'\nStage Progress Summary:')
        stages = ['conversation_boundary', 'parser', 'fact_extraction', 'metadata', 'merge']
        for stage in stages:
            result_count = session.query(StageResult).filter(StageResult.stage_name == stage).count()
            completed_count = session.query(StageCompletion).filter(
                StageCompletion.stage_name == stage,
                StageCompletion.status == 'completed'
            ).count()
            print(f'   {stage}: {result_count} results, {completed_count} processed by next stage')
        
        # Check remaining unprocessed
        from app.assistant.database.processed_entity_log import ProcessedEntityLog
        unprocessed = session.query(ProcessedEntityLog).filter(ProcessedEntityLog.processed == False).count()
        print(f'\nRemaining in processed_entity_log: {unprocessed} unprocessed')
        
        print("\n[OK] Database check completed!")
        
    except Exception as e:
        print(f"[ERR] Error checking database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == '__main__':
    """
    Run this file directly from IDE to check database results
    """
    check_database_results()
