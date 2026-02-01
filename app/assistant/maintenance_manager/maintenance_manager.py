from datetime import datetime, timedelta, timezone
import threading
from app.assistant.maintenance_manager.chat_summary import ChatSummaryRunner
from app.assistant.maintenance_manager.maintenance_tool_caller import MaintenanceToolCaller
from app.assistant.maintenance_manager.save_to_unified_db import save_to_unified_db
from app.assistant.maintenance_manager.daily_summary_scheduler import DailySummaryScheduler
from app.assistant.ServiceLocator.service_locator import DI
# from app.assistant.rag_pipeline.rag_processor import RAGProcessor  # DEPRECATED
from app.assistant.utils.logging_config import get_maintenance_logger
from app.assistant.utils.pydantic_classes import Message
from app.assistant.user_settings_manager.user_settings import can_run_feature

logger = get_maintenance_logger(__name__)


class MaintenanceManager:
    def __init__(self, name: str = "maintenance_manager"):

        self.name = name
        self.event_hub = DI.event_hub

        # ENABLED: Automatic maintenance tasks (for KG processing)
        self.event_hub.register_event("idle_mode", self.idle_mode_handler)

        self.tool_caller = MaintenanceToolCaller()

        # Dictionaries for rate limiting publish events
        self.last_publish_times = {}  # Stores the last publish time for each event
        self.publish_intervals = {
            'save_chat': timedelta(seconds=30),  # Rate limit chat saving to avoid unnecessary DB writes
            'summarize_chat': timedelta(seconds=300),
            'maintenance': timedelta(seconds=30),
            'system_state_monitor': timedelta(seconds=300),
            'action_decider': timedelta(seconds=240),
            'kg_processing': timedelta(minutes=15),
            'kg_explorer': timedelta(hours=2),
            'kg_repair_pipeline': timedelta(minutes=5),
            'taxonomy_processing': timedelta(minutes=20),
            'location_tracking': timedelta(minutes=30),  # Check location every 30 minutes
        }

        self.last_summary_time = datetime.now(timezone.utc)

        # Initialize daily summary scheduler for idle mode processing
        self.daily_summary_scheduler = DailySummaryScheduler()

        # Track if KG repair pipeline is currently running (to prevent concurrent runs)
        self.kg_repair_pipeline_running = False

        # Thread safety for maintenance operations
        self.processing_lock = threading.RLock()

    def should_summarize(self, messages) -> bool:
        """
        Only summarize when the *chat history* is actually bloated.

        Notes:
        - We avoid summarizing based on total message count because the global blackboard
          may contain many non-chat/system messages.
        - `is_chat` is the indicator used by EmiAgent's `history` injection.
        """
        try:
            chat_messages = [
                m for m in (messages or [])
                if getattr(m, "is_chat", False)
                and not set(getattr(m, "sub_data_type", []) or []).intersection(
                    {"history_summary", "entity_card_injection", "agent_notification"}
                )
            ]
        except Exception:
            chat_messages = messages or []

        # Conservative thresholds: only summarize when truly large.
        return len(chat_messages) > 250 or self.estimate_token_count(chat_messages) > 12000

    def estimate_token_count(self, messages) -> int:
        # Rough token estimate: 1 token ≈ 4 characters in English text
        total_chars = sum(len(msg.content or "") for msg in messages)
        return total_chars // 4

    def should_publish(self, event_name: str) -> bool:
        now = datetime.now(timezone.utc)
        last_time = self.last_publish_times.get(event_name, datetime.min.replace(tzinfo=timezone.utc))
        interval = self.publish_intervals.get(event_name, timedelta(seconds=30))
        if now - last_time >= interval:
            self.last_publish_times[event_name] = now
            return True
        return False

    def should_run_daily_summary(self) -> bool:
        """
        Check if daily summary should run (once per day, respects quiet_mode settings).
        
        Returns:
            bool: True if daily summary should run, False otherwise
        """
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        today = now.date()
        today_str = today.strftime("%Y-%m-%d")

        # Check if we've already run today (in-memory check)
        last_run_date = getattr(self, 'last_daily_summary_date', None)
        if last_run_date == today:
            logger.debug(f"⏸️ Daily summary skipped - already ran today")
            return False

        # Check if daily summary file already exists for today
        from app.assistant.maintenance_manager.daily_summary_storage import DailySummaryStorage
        storage = DailySummaryStorage()

        if storage.get_daily_summary(today_str) is not None:
            # File already exists, mark as run for today
            self.last_daily_summary_date = today
            logger.debug(f"⏸️ Daily summary skipped - file already exists for {today_str}")
            return False

        # Should run - mark the date
        logger.info(f"✅ Daily summary eligible to run for {today_str}")
        self.last_daily_summary_date = today
        return True

    def _is_tool_quiet_hours(self) -> bool:
        """
        Check if we're in quiet hours for tool calls using universal_hours from quiet_mode config.
        Returns True if tools should be disabled.
        """
        from app.assistant.user_settings_manager.user_settings import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Check if global quiet mode is enabled
        if not settings_manager.get("quiet_mode.enabled", False):
            return False
        
        # Use universal_hours from quiet_mode config
        universal_hours = settings_manager.get("quiet_mode.universal_hours", {})
        start_str = universal_hours.get("start", "23:00")
        end_str = universal_hours.get("end", "07:00")
        
        try:
            from zoneinfo import ZoneInfo
            now_local = datetime.now(ZoneInfo("America/Los_Angeles"))
            current_time = now_local.time()
            
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
            
            # Handle overnight ranges (e.g., 23:00 to 07:00)
            if start_time > end_time:
                # Overnight: quiet if current >= start OR current < end
                return current_time >= start_time or current_time < end_time
            else:
                # Same day: quiet if current >= start AND current < end
                return start_time <= current_time < end_time
        except Exception as e:
            logger.warning(f"Error parsing quiet hours: {e}, using default behavior")
            return False

    def _is_feature_in_quiet_hours(self, feature: str) -> bool:
        """
        Check if a feature is currently in quiet hours based on user settings.
        
        Args:
            feature: Feature name (e.g., 'kg', 'taxonomy', 'email')
            
        Returns:
            True if the feature should be disabled due to quiet hours.
        """
        from app.assistant.user_settings_manager.user_settings import get_settings_manager
        settings_manager = get_settings_manager()
        return settings_manager.is_quiet_mode_active(feature)

    def idle_mode_handler(self, idle_msg):
        logger.info("Idle mode triggered - running maintenance tasks.")

        # 1. Chat saving (rate limited, skip if KG or taxonomy is running)
        if self.should_publish("save_chat"):
            if getattr(self, 'kg_processing_running', False) or getattr(self, 'taxonomy_processing_running', False):
                logger.debug("⏸️ Skipping chat save - KG/taxonomy processing in progress")
            else:
                self.save_chat_history()

        # 2. Chat summarization (skip if KG or taxonomy is running to avoid database lock contention)
        if self.should_publish("summarize_chat"):
            if getattr(self, 'kg_processing_running', False) or getattr(self, 'taxonomy_processing_running', False):
                logger.debug("⏸️ Skipping chat summarization - KG/taxonomy processing in progress")
            elif getattr(self, 'chat_summary_running', False):
                logger.debug("⏸️ Chat summarization already running in background")
            else:
                messages = DI.global_blackboard.get_messages()
                if self.should_summarize(messages):
                    self._run_chat_summary_async()

        # 3. Tool execution (respects universal quiet hours from config, skip if KG/taxonomy/planner running)
        if self.should_publish("maintenance"):
            if getattr(self, 'kg_processing_running', False) or getattr(self, 'taxonomy_processing_running', False):
                logger.debug("⏸️ Skipping tool calls - KG/taxonomy processing in progress")
            elif DI.system_state_monitor and getattr(DI.system_state_monitor, 'planner_running', False):
                logger.debug("⏸️ Skipping tool calls - auto_planner is running")
            elif self._is_tool_quiet_hours():
                from zoneinfo import ZoneInfo
                now_local = datetime.now(ZoneInfo("America/Los_Angeles"))
                logger.info(f"⏸️ Tool quiet hours active - skipping tool calls (current time: {now_local.strftime('%H:%M %Z')})")
            else:
                self.tool_caller.call_next_tool_if_ready()

        # 4. System state monitoring (checks feature flag, skip if KG/taxonomy running)
        if self.should_publish("system_state_monitor"):
            if getattr(self, 'kg_processing_running', False) or getattr(self, 'taxonomy_processing_running', False):
                logger.debug("⏸️ Skipping system state monitor - KG/taxonomy processing in progress")
            elif getattr(self, 'system_state_monitor_running', False):
                logger.debug("⏸️ System state monitor already running in background")
            elif can_run_feature('system_state_monitor'):
                self._run_system_state_monitor_async()
            else:
                logger.debug("⏸️ System state monitor disabled in settings")

        # 5. RAG processing - DEPRECATED
        # if self.should_publish("rag_processing"):
        #     self.run_rag_processing()

        # 6. Knowledge Graph processing (respects feature flag, quiet hours, and running state)
        if self.should_publish("kg_processing"):
            if not can_run_feature('kg'):
                logger.info("⏸️ KG processing disabled in settings or missing OpenAI API key")
            elif self._is_feature_in_quiet_hours('kg'):
                logger.info("⏸️ KG processing skipped - quiet hours active")
            elif getattr(self, 'kg_processing_running', False):
                logger.info("⏸️ KG processing already running in background")
            else:
                self.run_kg_processing()

        # 7. Daily Summary processing (checks feature flag, quiet hours, & API keys, skip if KG/taxonomy running)
        if self.should_run_daily_summary():
            if getattr(self, 'kg_processing_running', False) or getattr(self, 'taxonomy_processing_running', False):
                logger.debug("⏸️ Skipping daily summary - KG/taxonomy processing in progress")
            elif not can_run_feature('daily_summary'):
                logger.info("⏸️ Daily summary disabled in settings or missing required API keys (Google, OpenAI)")
            elif self._is_feature_in_quiet_hours('daily_summary'):
                logger.info("⏸️ Daily summary skipped - quiet hours active")
            else:
                self.run_daily_summary()

        # 8. Taxonomy processing (respects feature flag, quiet hours, and running state)
        if self.should_publish("taxonomy_processing"):
            if not can_run_feature('taxonomy'):
                logger.info("⏸️ Taxonomy processing disabled in settings or missing OpenAI API key")
            elif self._is_feature_in_quiet_hours('taxonomy'):
                logger.info("⏸️ Taxonomy processing skipped - quiet hours active")
            elif getattr(self, 'taxonomy_processing_running', False):
                logger.info("⏸️ Taxonomy processing already running in background")
            else:
                self.run_taxonomy_processing()

        # 9. Knowledge Graph Explorer - DISABLED
        # if self.should_publish("kg_explorer"):
        #     self.run_kg_explorer()

        # 12. KG REPAIR PIPELINE (DISABLED)
        # if self.should_publish("kg_repair_pipeline"):
        #     self.run_kg_repair_pipeline()

    def scheduler_event_handler(self, event_msg):
        """
        Handle scheduler events, specifically daily summary events.
        Respects universal quiet hours from config for non-critical events.
        """
        try:
            # Check if we're in quiet hours for scheduler events (uses universal_hours from config)
            if self._is_tool_quiet_hours():
                from zoneinfo import ZoneInfo
                now_local = datetime.now(ZoneInfo("America/Los_Angeles"))
                logger.info(f"⏸️ Scheduler quiet hours active - ignoring scheduler event (current time: {now_local.strftime('%H:%M %Z')})")
                return
            
            event_data = event_msg.data
            if not event_data:
                logger.warning("Scheduler event missing data")
                return

            event_payload = event_data.get("event_payload", {})
            task = event_payload.get("task")

            if task == "daily_summary":
                logger.info("🕖 Daily summary event received from scheduler")
                self.run_daily_summary()
            else:
                logger.info(f"Scheduler event received for task: {task}")

        except Exception as e:
            logger.error(f"Error handling scheduler event: {e}")

    def save_chat_history(self):
        with self.processing_lock:
            global_black_board = DI.global_blackboard
            global_black_board_messages = global_black_board.get_messages()

            chat_messages = [
                msg for msg in global_black_board_messages
                if msg.is_chat
                   and not set(getattr(msg, "sub_data_type", []) or []).intersection(
                        {"history_summary", "entity_card_injection", "agent_notification"}
                   )
                   and msg.content
                   and not getattr(msg, 'test_mode', False)  # Skip messages with test_mode flag
            ]

            if len(chat_messages) == 0:
                logger.info("No chat messages to save.")
                return

            # Check if we have any new messages since last save
            try:
                latest_msg_time = max(m.timestamp for m in chat_messages)
                # Only skip if we have messages and the latest is older than our last save time
                if latest_msg_time <= self.last_summary_time:
                    logger.info("No new chat messages since last summary. Skipping summarization.")
                    return
            except Exception as e:
                logger.error(f"Error checking message timestamps: {e}")
                # If there's an error with timestamps, still try to save the messages
                pass

            result = []
            for msg in chat_messages:
                data = {
                    'id': msg.id,
                    'timestamp': msg.timestamp,
                    'role': getattr(msg, "role", None) or 'unknown',
                    'message': msg.content,
                    'source': "chat",
                    'processed': False,
                }

                result.append(data)

            if len(result) == 0:
                logger.info("No chat messages to save.")
                return

            # Update the last summary time before saving to avoid race conditions
            self.last_summary_time = datetime.now(timezone.utc)
            save_to_unified_db(result, "chat")

    # =========================================================================
    # Async Wrappers for Long-Running Tasks
    # These run in background threads to avoid blocking the EventHandlerHub
    # =========================================================================

    def _run_chat_summary_async(self):
        """Run chat summarization in background thread."""
        self.chat_summary_running = True
        thread = threading.Thread(target=self._chat_summary_worker, daemon=True)
        thread.start()
        logger.info("💬 Started chat summarization in background thread")

    def _chat_summary_worker(self):
        """Background worker for chat summarization."""
        try:
            logger.info("💬 Chat summarization background worker started")
            ChatSummaryRunner(DI.global_blackboard).run()
            logger.info("💬 Chat summarization completed")
        except Exception as e:
            logger.error(f"❌ Error in chat summarization: {e}", exc_info=True)
        finally:
            self.chat_summary_running = False

    def _run_system_state_monitor_async(self):
        """Run system state monitor in background thread."""
        self.system_state_monitor_running = True
        thread = threading.Thread(target=self._system_state_monitor_worker, daemon=True)
        thread.start()
        logger.info("🔍 Started system state monitor in background thread")

    def _system_state_monitor_worker(self):
        """Background worker for system state monitor."""
        try:
            logger.info("🔍 System state monitor background worker started")
            DI.system_state_monitor.run()
            logger.info("🔍 System state monitor completed")
        except AttributeError:
            logger.info("System state monitor not available")
        except Exception as e:
            logger.error(f"❌ Error in system state monitor: {e}", exc_info=True)
        finally:
            self.system_state_monitor_running = False

    def _run_location_tracking_async(self):
        """Run location tracking in background thread."""
        self.location_tracking_running = True
        thread = threading.Thread(target=self._location_tracking_worker, daemon=True)
        thread.start()
        logger.info("📍 Started location tracking in background thread")

    def _location_tracking_worker(self):
        """Background worker for location tracking."""
        try:
            logger.info("📍 Location tracking background worker started")
            self.run_location_tracking()
        except Exception as e:
            logger.error(f"❌ Error in location tracking worker: {e}", exc_info=True)
        finally:
            self.location_tracking_running = False
            logger.info("📍 Location tracking background worker finished")

    def setup_daily_summary_schedule(self):
        """
        Set up the daily summary to run at 7am every day.
        """
        try:
            # Get the scheduler service
            scheduler_service = DI.scheduler
            if not scheduler_service:
                logger.warning("Scheduler service not available. Daily summary scheduling skipped.")
                return

            event_scheduler = scheduler_service.get_event_scheduler()

            # Create daily summary event (7am every day)
            from app.assistant.scheduler.pydantic_types.base_event_data import BaseEventData

            # Calculate next 7am
            now = datetime.now(timezone.utc)
            next_7am = now.replace(hour=7, minute=0, second=0, microsecond=0)
            if now.hour >= 7:
                next_7am += timedelta(days=1)

            daily_summary_event = BaseEventData(
                event_id="daily_summary_7am",
                event_type="interval",
                interval=24 * 60 * 60,  # 24 hours in seconds
                start_date=next_7am.isoformat(),
                end_date=None,  # Run indefinitely
                event_payload={
                    "task": "daily_summary",
                    "description": "Generate daily summary at 7am"
                }
            )

            # Create the event
            result = event_scheduler.create_event(daily_summary_event)
            logger.info(f"Daily summary schedule setup: {result}")

        except Exception as e:
            logger.error(f"Failed to setup daily summary schedule: {e}")

    def run_daily_summary(self):
        """
        Execute the daily summary generation in a background thread.
        Called by idle mode handler between 6am-5pm, once per day.
        
        Runs in a separate thread to avoid blocking the EventHandlerHub worker,
        which would delay socket emissions and other events.
        """
        # Check if already running
        if getattr(self, 'daily_summary_running', False):
            logger.info("⏸️ Daily summary already running in background - skipping")
            return {"success": False, "error": "Already running"}
        
        # Mark as running and spawn thread
        self.daily_summary_running = True
        thread = threading.Thread(target=self._daily_summary_worker, daemon=True)
        thread.start()
        logger.info("📋 Started daily summary in background thread")
        return {"success": True, "message": "Started in background"}
    
    def _daily_summary_worker(self):
        """Background worker for daily summary processing."""
        try:
            logger.info("🕖 Daily summary background worker started")
            result = self.daily_summary_scheduler.run_daily_summary()

            if result.get("success"):
                logger.info("✅ Daily summary completed successfully")
            else:
                logger.error(f"❌ Daily summary failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"❌ Error in daily summary execution: {e}")
        finally:
            self.daily_summary_running = False
            logger.info("📋 Daily summary background worker finished")

    def run_rag_processing(self):
        # DEPRECATED: RAG processing has been replaced by the knowledge graph pipeline
        logger.info("🚫 RAG processing is deprecated and disabled")
        return {
            'message': 'RAG processing is deprecated and disabled',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    def run_kg_processing(self):
        """
        Process unified_log messages through knowledge graph pipeline.
        This includes entity resolution and knowledge graph building.
        
        Eligibility is controlled by:
        - Feature flag (enable_kg in settings)
        - Quiet hours (per-feature quiet hours in settings)
        - Not already running (kg_processing_running flag)
        - Rate limiting (15 min interval via should_publish)
        
        Runs in a separate thread to avoid blocking other maintenance tasks.
        """
        # Check if a KG processing thread is already running (double-check)
        if getattr(self, 'kg_processing_running', False):
            logger.info("⏸️ KG processing already running in background - skipping")
            return

        # Mark as running and spawn thread
        self.kg_processing_running = True
        thread = threading.Thread(target=self._kg_processing_worker, daemon=True)
        thread.start()
        logger.info("🧠 Started knowledge graph processing in background thread")

    def _kg_processing_worker(self):
        """Background worker for KG processing"""
        kg_utils = None
        try:
            logger.info("🧠 Starting knowledge graph processing...")

            # Step 1: Entity resolution (unified_log → processed_entity_log)
            from app.assistant.kg_core.log_preprocessing import process_unified_log_chunks_with_entity_resolution

            entity_result = process_unified_log_chunks_with_entity_resolution(
                chunk_size=8,
                overlap_size=3,
                source_filter='chat',  # Only process chat messages
                role_filter=['user', 'assistant']
            )

            logger.info(f"✅ Entity resolution completed: {entity_result}")

            # Step 2: Knowledge graph processing (processed_entity_log → KG)
            from app.assistant.kg_core.kg_pipeline import process_all_processed_entity_logs_to_kg

            kg_result = process_all_processed_entity_logs_to_kg(
                batch_size=100,
                max_batches=1,  # Process one batch per idle cycle to avoid blocking
                role_filter=['user', 'assistant']
            )

            logger.info(f"✅ Knowledge graph processing completed: {kg_result}")

        except Exception as e:
            logger.error(f"❌ Error in KG processing: {e}")
        finally:
            # Ensure session is closed even on error
            if kg_utils:
                kg_utils.close_session()
            self.kg_processing_running = False

    def run_taxonomy_processing(self):
        """
        Process unclassified nodes through the taxonomy pipeline.
        This classifies nodes into the taxonomy hierarchy during idle time.
        Runs in a separate thread to avoid blocking other maintenance tasks.
        """
        # Check if a taxonomy processing thread is already running
        if getattr(self, 'taxonomy_processing_running', False):
            logger.debug("⏸️ Taxonomy processing already running in background - skipping")
            return

        # Mark as running and spawn thread
        self.taxonomy_processing_running = True
        thread = threading.Thread(target=self._taxonomy_processing_worker, daemon=True)
        thread.start()
        logger.info("🏷️ Started taxonomy processing in background thread")

    def _taxonomy_processing_worker(self):
        """Background worker for taxonomy processing"""
        try:
            logger.info("🏷️ Starting taxonomy processing...")

            # Import the taxonomy pipeline function
            from app.assistant.kg_core.taxonomy.taxonomy_pipeline import process_unclassified_nodes_batch

            # Process a batch of unclassified nodes
            # Using a smaller batch size for idle processing to avoid overwhelming the system
            result = process_unclassified_nodes_batch(
                batch_size=50,  # Smaller batch for idle processing
                node_type=None  # Process all node types
            )

            if result.get('nodes_processed', 0) > 0:
                logger.info(f"✅ Taxonomy processing completed: {result}")
            else:
                logger.info("📭 No unclassified nodes found for taxonomy processing")

        except Exception as e:
            logger.error(f"❌ Error in taxonomy processing: {e}")
        finally:
            self.taxonomy_processing_running = False

    def run_location_tracking(self):
        """
        Build/refresh the location timeline based on calendar events.
        
        This runs periodically to predict where the user will be throughout
        the day based on calendar events with locations. Other agents can
        query: "Where will user be in 2 hours?"
        """
        print("📍 run_location_tracking() called")
        logger.info("📍 run_location_tracking() starting...")
        try:
            from app.assistant.location_manager.location_manager import get_location_manager
            
            location_manager = get_location_manager()
            print("📍 Got location manager, calling refresh()...")
            
            # Rebuild timeline from calendar and infer gaps
            current = location_manager.refresh()
            
            # Log summary
            summary = location_manager.get_location_summary(hours_ahead=12)
            print(f"📍 Location timeline refreshed:\n{summary}")
            logger.info(f"📍 Location timeline refreshed:\n{summary}")
            
        except Exception as e:
            print(f"❌ Error in location tracking: {e}")
            logger.error(f"❌ Error in location tracking: {e}", exc_info=True)

    def run_kg_explorer(self):
        """
        Run the Knowledge Graph Explorer to analyze the KG and generate insights.
        """
        try:
            logger.info("🔍 Starting KG Explorer analysis...")

            # Create and run the KG Explorer manager
            kg_explorer_manager = DI.multi_agent_manager_factory.create_manager("kg_explorer_manager")

            # Set up exploration parameters
            exploration_input = {
                "exploration_scope": "full",
                "focus_areas": ["missing_dates", "orphaned_nodes", "data_quality", "weak_connections"]
            }

            # Run the exploration
            result = kg_explorer_manager.request_handler(
                Message(
                    task=f"Explore and analyze the knowledge graph with focus on: {exploration_input['focus_areas']}")
            )

            if result:
                logger.info(f"✅ KG Explorer completed: {result.content}")

                # Save exploration results (optional - could save to a file or database)
                self._save_exploration_results(result)

                return {
                    'exploration_result': result.content,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            else:
                logger.warning("⚠️ KG Explorer returned no results")
                return {
                    'status': 'no_results',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

        except Exception as e:
            logger.error(f"❌ Error in KG Explorer: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    def _save_exploration_results(self, result):
        """
        Save KG exploration results to a file for review.
        """
        try:
            from app.assistant.maintenance_manager.daily_summary_storage import DailySummaryStorage

            # Create a timestamped filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"kg_exploration_{timestamp}.json"

            # Save to the daily_summaries directory
            import os
            summaries_dir = os.path.join(os.path.dirname(__file__), "..", "..", "daily_summaries")
            os.makedirs(summaries_dir, exist_ok=True)

            filepath = os.path.join(summaries_dir, filename)

            exploration_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "analysis": result.content,
                "type": "kg_exploration"
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                import json
                json.dump(exploration_data, f, indent=2, ensure_ascii=False)

            logger.info(f"📁 KG exploration results saved to: {filepath}")

        except Exception as e:
            logger.error(f"❌ Error saving exploration results: {e}")

    def run_kg_repair_pipeline(self):
        """
        Run the KG Repair Pipeline to identify and fix problematic nodes.
        
        This is the main entry point for the pipeline, providing Flask + DI context
        needed for the questioner stage (ask_user tool) and implementer stage (kg_team).
        """
        # Prevent concurrent pipeline runs
        if self.kg_repair_pipeline_running:
            logger.info("⏸️ KG Repair Pipeline already running - skipping this cycle")
            return

        try:
            self.kg_repair_pipeline_running = True
            logger.info("🔧 Starting KG Repair Pipeline...")

            from app.assistant.kg_repair_pipeline.pipeline_orchestrator import KGPipelineOrchestrator

            # Create the orchestrator
            orchestrator = KGPipelineOrchestrator()

            # Run the pipeline (max 1 node per run for fast testing)
            pipeline_state = orchestrator.run_pipeline(max_nodes=1)

            # Log results
            logger.info(f"✅ KG Repair Pipeline completed:")
            logger.info(f"   Nodes identified: {pipeline_state.total_nodes_identified}")
            logger.info(f"   Nodes validated: {pipeline_state.nodes_validated}")
            logger.info(f"   Nodes questioned: {pipeline_state.nodes_questioned}")
            logger.info(f"   Nodes resolved: {pipeline_state.nodes_resolved}")
            logger.info(f"   Nodes skipped: {pipeline_state.nodes_skipped}")
            logger.info(f"   Errors: {len(pipeline_state.errors)}")

            # Save pipeline results
            self._save_pipeline_results(pipeline_state)

            return {
                'success': True,
                'nodes_identified': pipeline_state.total_nodes_identified,
                'nodes_validated': pipeline_state.nodes_validated,
                'nodes_questioned': pipeline_state.nodes_questioned,
                'nodes_resolved': pipeline_state.nodes_resolved,
                'nodes_skipped': pipeline_state.nodes_skipped,
                'errors': pipeline_state.errors,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Error in KG Repair Pipeline: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        finally:
            # Always clear the running flag
            self.kg_repair_pipeline_running = False

    def _save_pipeline_results(self, pipeline_state):
        """
        Save KG repair pipeline results to a file for review.
        """
        try:
            import os
            import json

            # Create a timestamped filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"kg_repair_pipeline_{timestamp}.json"

            # Save to the kg_repair_pipeline directory
            results_dir = os.path.join(os.path.dirname(__file__), "..", "kg_repair_pipeline", "results")
            os.makedirs(results_dir, exist_ok=True)

            filepath = os.path.join(results_dir, filename)

            pipeline_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nodes_identified": pipeline_state.total_nodes_identified,
                "nodes_validated": pipeline_state.nodes_validated,
                "nodes_questioned": pipeline_state.nodes_questioned,
                "nodes_resolved": pipeline_state.nodes_resolved,
                "nodes_skipped": pipeline_state.nodes_skipped,
                "errors": pipeline_state.errors,
                "processed_nodes": [
                    {
                        "node_id": node.id,
                        "label": node.label,
                        "status": node.status,
                        "problem_description": node.problem_description,
                        "resolution_notes": node.resolution_notes
                    }
                    for node in pipeline_state.problematic_nodes
                ]
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(pipeline_data, f, indent=2, ensure_ascii=False)

            logger.info(f"📁 Pipeline results saved to: {filepath}")

        except Exception as e:
            logger.error(f"❌ Error saving pipeline results: {e}")
