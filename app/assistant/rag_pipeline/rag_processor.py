# app/assistant/rag_pipeline/rag_processor.py
from typing import Optional
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.rag_pipeline.source_log_handler import SourceLogHandler
from app.assistant.rag_pipeline.rag_db_handler import RAGDBHandler

from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class RAGProcessor:
    def __init__(
            self,
            source_name=None,
            agent_name="rag_extract_chat",
            log_handler: Optional[SourceLogHandler] = None,
            rag_handler: Optional[RAGDBHandler] = None
    ):
        self.source_model = UnifiedLog
        self.source_name = source_name
        self.agent_name = agent_name
        self.log_handler = log_handler or SourceLogHandler()
        self.rag_handler = rag_handler or RAGDBHandler()

    def run(self, batch_size: int = 100, max_chars: int = 8000) -> None:
        if self.source_name is None:
            # Run grouped by source
            grouped_logs = self.log_handler.fetch_all_unprocessed_logs_grouped_by_source(self.source_model)
            for source, logs in grouped_logs.items():
                logger.info(f"Processing source: {source} with {len(logs)} entries")
                processor = RAGProcessor(source_name=source)
                processor._process_logs(logs, batch_size, max_chars)
        else:
            logs = self.log_handler.fetch_unprocessed_logs(self.source_model, self.source_name)
            self._process_logs(logs, batch_size, max_chars)

    # Context grouping by time might be better

    def _build_char_limited_batch(self, logs, max_chars: int):
        total_chars = 0
        batch = []
        remainder = []

        for i, log in enumerate(logs):
            content = log.get("message", "") or ""
            entry_len = len(content)

            if entry_len > max_chars:
                logger.warning(f"[{self.source_name}] Skipping oversized log entry.")
                continue

            if total_chars + entry_len > max_chars:
                remainder = logs[i:]
                break

            batch.append(log)
            total_chars += entry_len

        return batch, remainder

    def _process_logs(self, all_logs, batch_size, max_chars):
        last_ts = None

        while all_logs:
            batch, all_logs = self._build_char_limited_batch(all_logs, max_chars)
            if not batch:
                break

            input_text = "\n".join(log.get("message", "").strip() for log in batch if log.get("message"))

            if not input_text:
                logger.warning(f"[{self.source_name}] Skipping empty input batch.")
                continue

            msg = Message(agent_input=input_text)

            agent = DI.agent_factory.create_agent(self.agent_name)
            extracted_info = agent.action_handler(msg)
            data = extracted_info.data_list

            facts = []
            for item in data:
                facts.extend(item.get("info", []))

            if facts:
                self.rag_handler.insert_rag_facts(facts, self.source_name)
            else:
                logger.info(f"[{self.source_name}] Extractor returned no info.")

            self.log_handler.mark_processed(self.source_model, batch)
            last_ts = batch[-1]["timestamp"]

        logger.info(f"[{self.source_name}] RAG processing complete.")


