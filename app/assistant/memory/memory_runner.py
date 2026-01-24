"""
MemoryRunner: Processes extracted facts and updates resource files.

Picks up unprocessed facts from extracted_facts table and invokes the
memory_manager multi-agent system to intelligently update the appropriate files.
"""

from pathlib import Path
from typing import Any, Dict, List, TypedDict

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.pydantic_classes import Message
from app.assistant.database.db_handler import ExtractedFact
from app.models.base import get_session

logger = get_logger(__name__)


class UnprocessedFact(TypedDict):
    id: str
    summary: str
    category: str
    tags: Any
    source_message_ids: Any


class MemoryRunner:
    """
    Processes extracted facts and updates user memory/preference files.

    Invokes the memory_manager multi-agent system which:
    1. Uses tag routing to pick the correct file(s)
    2. Uses json_finder to locate relevant JSON paths
    3. Uses json_editor to decide edits
    4. Applies edits via MemoryJsonHandler
    """

    def __init__(self, resources_dir: Path | None = None):
        self._resources_dir = resources_dir or get_resources_dir()

    def _get_unprocessed_facts(self, limit: int = 5) -> List[UnprocessedFact]:
        """Get unprocessed facts from extracted_facts table (return plain dicts)."""
        session = get_session()
        try:
            rows = (
                session.query(
                    ExtractedFact.id,
                    ExtractedFact.summary,
                    ExtractedFact.category,
                    ExtractedFact.tags,
                    ExtractedFact.source_message_ids,
                )
                    .filter(
                    ExtractedFact.processed.is_(False),
                    ExtractedFact.category.in_(["preference", "feedback"]),
                )
                    .order_by(ExtractedFact.created_at.asc())
                    .limit(limit)
                    .all()
            )

            return [
                {
                    "id": r.id,
                    "summary": r.summary,
                    "category": r.category,
                    "tags": r.tags,
                    "source_message_ids": r.source_message_ids,
                }
                for r in rows
            ]
        finally:
            session.close()

    def _mark_fact_processed(self, fact_id: str) -> None:
        """Mark a fact as processed."""
        session = get_session()
        try:
            fact = session.query(ExtractedFact).filter(ExtractedFact.id == fact_id).first()
            if not fact:
                return
            fact.processed = True
            session.commit()
            logger.info(f"🧠 MEMORY: Marked fact {fact_id} as processed")
        except Exception as e:
            session.rollback()
            logger.error(f"🧠 MEMORY: Error marking fact as processed: {e}", exc_info=True)
        finally:
            session.close()

    def _fetch_raw_messages(self, message_ids: List[str]) -> str:
        """
        Fetch raw message text from unified_log for given message IDs.

        Returns a formatted string of messages with timestamps and roles.
        """
        from app.assistant.database.db_handler import UnifiedLog

        session = get_session()
        try:
            if not message_ids:
                return "[No source messages available]"

            messages = (
                session.query(UnifiedLog)
                    .filter(UnifiedLog.id.in_(message_ids))
                    .order_by(UnifiedLog.timestamp)
                    .all()
            )

            if not messages:
                return "[Source messages not found in database]"

            formatted: List[str] = []
            for msg in messages:
                role = msg.role or "unknown"
                timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S") if msg.timestamp else "unknown time"
                formatted.append(f"[{timestamp}] {role}: {msg.message}")

            return "\n".join(formatted)

        except Exception as e:
            logger.error(f"🧠 MEMORY: Error fetching raw messages: {e}", exc_info=True)
            return f"[Error fetching messages: {e}]"
        finally:
            session.close()

    def _load_json_file(self, file_path: str) -> Dict[str, Any]:
        """Load JSON file from resources directory safely."""
        import json

        rel = Path(file_path)

        # Disallow absolute paths and path traversal
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Invalid JSON file path: {file_path}")

        full_path = (self._resources_dir / rel).resolve()
        resources_root = self._resources_dir.resolve()

        # Ensure path stays under resources directory
        if resources_root not in full_path.parents and full_path != resources_root:
            raise ValueError(f"JSON file path escapes resources dir: {file_path}")

        if not full_path.exists():
            raise FileNotFoundError(f"JSON file not found: {full_path}")

        with full_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _process_single_fact(self, fact: UnprocessedFact) -> Dict[str, Any]:
        """
        Process a single extracted fact using finder + editor agents.

        Flow:
        1. Fetch raw messages for context
        2. Use tag router to find target JSON files
        3. For each target file:
           a. Call json_finder to locate relevant JSON paths
           b. Call json_editor to decide edits (delete/update/insert)
        4. Execute edits via MemoryJsonHandler
        """
        logger.info(f"🧠 MEMORY: Processing fact: {fact['summary'][:60]}...")
        logger.info(f"🧠 MEMORY:   Category: {fact['category']}, Tags: {fact['tags']}")

        try:
            raw_messages = self._fetch_raw_messages(fact["source_message_ids"])

            from app.assistant.memory.tag_router import get_tag_router
            tag_router = get_tag_router()

            target_files = tag_router.get_target_files_for_fact(
                {
                    "tags": fact["tags"],
                    "temporal_scope": "chronic",
                }
            )

            if not target_files:
                logger.warning(f"🧠 MEMORY: No files subscribe to tags {fact['tags']}")
                return {
                    "success": True,
                    "fact_id": fact["id"],
                    "summary": fact["summary"],
                    "action": "no_target_files",
                }

            logger.info(f"🧠 MEMORY:   Target files: {target_files}")

            finder = DI.agent_factory.create_agent("memory::json_finder")
            editor = DI.agent_factory.create_agent("memory::json_editor")
            if not finder or not editor:
                raise RuntimeError("json_finder or json_editor agent not found")

            all_edits: List[Dict[str, Any]] = []
            import json as json_lib

            for target_file in target_files:
                logger.info(f"🧠 MEMORY:   Processing {target_file}...")

                json_content = self._load_json_file(target_file)
                json_str = json_lib.dumps(json_content, indent=2)

                finder_response = finder.action_handler(
                    Message(
                        agent_input={
                            "json_content": json_str,
                            "query": fact["summary"],
                            "raw_messages": raw_messages,
                        }
                    )
                )

                finder_data = (finder_response.data or {}) if finder_response else {}
                locations = finder_data.get("locations", []) or []
                suggested_insert_path = finder_data.get("suggested_insert_path", None)
                finder_reasoning = finder_data.get("reasoning", "N/A")

                if not isinstance(locations, list):
                    logger.warning(
                        f"🧠 MEMORY: Finder returned non-list locations for {target_file}: {type(locations)}"
                    )
                    locations = []

                logger.info(
                    f"🧠 MEMORY:     Finder: {len(locations)} location(s), reasoning: {finder_reasoning}"
                )

                editor_response = editor.action_handler(
                    Message(
                        agent_input={
                            "json_content": json_str,
                            "query": fact["summary"],
                            "raw_messages": raw_messages,
                            "found_locations": locations,
                            "suggested_insert_path": suggested_insert_path,
                        }
                    )
                )

                editor_data = (editor_response.data or {}) if editor_response else {}
                edits = editor_data.get("edits", []) or []
                decision = editor_data.get("decision", None)
                editor_reasoning = editor_data.get("reasoning", "N/A")

                if not decision:
                    raise RuntimeError("Editor did not return 'decision' field")

                logger.info(
                    f"🧠 MEMORY:     Editor decision: {decision}, reasoning: {editor_reasoning}"
                )

                if decision == "reject":
                    logger.info(f"🧠 MEMORY:     Rejected edits for {target_file}")
                    continue

                if edits and not isinstance(edits, list):
                    logger.warning(
                        f"🧠 MEMORY: Editor returned non-list edits for {target_file}: {type(edits)}"
                    )
                    edits = []

                if edits:
                    file_edits = [{**edit, "file": target_file} for edit in edits]
                    all_edits.extend(file_edits)
                    logger.info(f"🧠 MEMORY:     Added {len(file_edits)} edit(s) for {target_file}")

            if not all_edits:
                logger.info("🧠 MEMORY:   No edits to execute")
                return {
                    "success": True,
                    "fact_id": fact["id"],
                    "action": "no_edits",
                }

            logger.info(f"🧠 MEMORY:   Executing {len(all_edits)} total edit(s)...")

            from app.assistant.memory.memory_json_handler import get_memory_json_handler
            handler = get_memory_json_handler()

            execution_result = handler.execute_edits(all_edits)

            logger.info(f"🧠 MEMORY:   ✅ Execution result: {execution_result.get('success')}")
            for i, edit_result in enumerate(execution_result.get("results", [])):
                logger.info(
                    f"🧠 MEMORY:     Edit {i+1}: {edit_result.get('operation')} - "
                    f"{edit_result.get('action', edit_result.get('error'))}"
                )

            return {
                "success": execution_result.get("success", False),
                "fact_id": fact["id"],
                "summary": fact["summary"],
                "edits_executed": len(all_edits),
                "results": execution_result.get("results", []),
            }

        except Exception as e:
            logger.error(f"🧠 MEMORY: ❌ Error processing fact: {e}", exc_info=True)
            return {
                "success": False,
                "fact_id": fact["id"],
                "summary": fact["summary"],
                "error": str(e),
            }

    def run(self, max_facts: int = 3) -> Dict[str, Any]:
        """
        Main entry point: Process unprocessed facts.

        Args:
            max_facts: Maximum number of facts to process in one run

        Returns:
            Dict with processing stats
        """
        logger.info("🧠 MEMORY: Starting memory processing run...")

        facts = self._get_unprocessed_facts(limit=max_facts)

        if not facts:
            logger.info("🧠 MEMORY: No unprocessed facts to process")
            return {
                "processed": 0,
                "success": 0,
                "failed": 0,
                "message": "No unprocessed facts",
            }

        logger.info(f"🧠 MEMORY: Found {len(facts)} unprocessed facts")

        success_count = 0
        failed_count = 0
        results: List[Dict[str, Any]] = []

        for fact in facts:
            result = self._process_single_fact(fact)
            results.append(result)

            if result.get("success"):
                success_count += 1
            else:
                failed_count += 1

            # You prefer no retries; mark processed either way.
            self._mark_fact_processed(fact["id"])

        logger.info(f"🧠 MEMORY: ✅ Completed: {success_count} succeeded, {failed_count} failed")

        return {
            "processed": len(facts),
            "success": success_count,
            "failed": failed_count,
            "results": results,
        }


def run_memory_processing(max_facts: int = 3) -> Dict[str, Any]:
    """Run memory processing (for use in background tasks)."""
    runner = MemoryRunner()
    return runner.run(max_facts=max_facts)
