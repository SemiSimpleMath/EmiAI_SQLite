import logging
from typing import List, Dict, Any, Optional, Type, Iterable
from sqlalchemy import select, func
from app.models.base import get_session
from datetime import date

logger = logging.getLogger(__name__)

class SourceLogHandler:
    def fetch_unprocessed_logs(
            self,
            source_model: Type,
            source_name: str,
            last_processed_timestamp: Optional = None,
            batch_size: int = 100,
            filter_roles: Optional[Iterable[str]] = None
    ) -> List[Dict[str, Any]]:
        db_session = get_session()
        try:
            query = select(source_model).where(
                source_model.processed == False,
                source_model.source == source_name
            )
            if filter_roles:
                query = query.where(source_model.role.in_(filter_roles))
            if last_processed_timestamp:
                query = query.where(source_model.timestamp > last_processed_timestamp)
            query = query.order_by(source_model.timestamp.asc()).limit(batch_size)
            results = db_session.execute(query).scalars().all()
            return [
                {
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "message": getattr(log, "message", None),
                    "role": getattr(log, "role", None)
                }
                for log in results
            ]
        except Exception as e:
            logger.error(f"[{source_name}] Error fetching logs: {e}")
            return []
        finally:
            db_session.close()

    def count_unprocessed_logs(self, model, source_name, filter_roles=None):
        try:
            session = get_session()
            query = session.query(model).filter(
                model.source == source_name,
                model.processed == False
            )
            if filter_roles:
                query = query.filter(model.role.in_(filter_roles))
            return query.count()
        except Exception as e:
            logger.error(f"[{source_name}] Error counting unprocessed logs: {e}")
            return 0
        finally:
            if 'session' in locals():
                session.close()



    def mark_processed(self, source_model: Type, logs: List[Dict[str, Any]]) -> None:
        if not logs:
            return
        db_session = get_session()
        try:
            ids = [log["id"] for log in logs]
            db_session.query(source_model).filter(
                source_model.id.in_(ids)
            ).update({source_model.processed: True}, synchronize_session=False)
            db_session.commit()
        except Exception as e:
            db_session.rollback()
            logger.error(f"Error marking logs as processed: {e}")
        finally:
            db_session.close()

    def fetch_all_unprocessed_logs_grouped_by_source(
            self,
            source_model: Type,
            filter_roles: Optional[Iterable[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        db_session = get_session()
        try:
            query = select(source_model).where(source_model.processed == False)
            if filter_roles:
                query = query.where(source_model.role.in_(filter_roles))
            query = query.order_by(source_model.timestamp.asc())
            results = db_session.execute(query).scalars().all()
            grouped = {}
            for log in results:
                src = getattr(log, "source", None)
                if not src:
                    continue
                grouped.setdefault(src, []).append({
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "message": getattr(log, "message", None),
                    "role": getattr(log, "role", None)
                })
            return grouped
        finally:
            db_session.close()

    def fetch_unprocessed_logs_by_date(
            self,
            source_model: Type,
            source_name: str,
            batch_date: date,
            filter_roles: Optional[Iterable[str]] = None,
            batch_size: int = 100
    ) -> List[Dict[str, Any]]:
        db_session = get_session()
        try:
            query = select(source_model).where(
                source_model.processed == False,
                source_model.source == source_name,
                func.date(source_model.timestamp) == batch_date
            )
            if filter_roles:
                query = query.where(source_model.role.in_(filter_roles))
            query = query.order_by(source_model.timestamp.asc()).limit(batch_size)
            results = db_session.execute(query).scalars().all()
            return [
                {
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "message": getattr(log, "message", None),
                    "role": getattr(log, "role", None)
                }
                for log in results
            ]
        finally:
            db_session.close()

