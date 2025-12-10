"""
system_state_monitor.py

This module implements a proactive system state monitor that checks for changes in the
repository and, if updates have occurred since the last planner run, collects the new data,
packages it along with the current system state and today’s action log, and then triggers
the auto_planner_manager. The planner’s output is then recorded in the database.

Assumptions:
- EventRepositoryManager provides:
    - search_events(data_type)
    - get_new_events(category, since_dt)
    - get_last_altered_by_data_type() returning a dict {data_type: last_altered_datetime}
- Pruning functions exist for calendar, email, and todo_task data:
    - prune_calendar_events(events)
    - prune_email_events(events)
    - prune_todo_events(events)
- For scheduler events, filter_scheduler_events() and summarize_repeating_events() are used.
- The auto_planner_manager can be invoked via ManagerInterface.create(...).run(input_package)
- Logged actions are recorded in AgentActivityLog via a SQLAlchemy session.
- utc_to_local() converts UTC datetimes to your local timezone.
"""
from datetime import timezone, timedelta
import json
from datetime import datetime
import uuid

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import ToolResult, Message, ToolMessage
from app.assistant.utils.time_utils import utc_to_local
from app.assistant.event_repository.prune_repo_events import (
    prune_calendar_events,
    prune_email_events,
    prune_todo_events,
    filter_scheduler_events,
    summarize_repeating_events,
    prune_scheduler_events
)
from app.assistant.event_repository.event_repository import EventRepositoryManager
from app.assistant.database.db_handler import AgentActivityLog
from app.models.base import get_session
from app.assistant.unified_item_manager import UnifiedItemManager
from app.assistant.unified_item_manager.process_new_recurring_events import process_new_recurring_events

# For triggering the auto planner

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

AUTO_PLANNER_AGENT_NAME = "AutoPlannerManager"
AUTO_PLANNER_GROUP = "auto_planner_group"  # you can customize/group as needed


class SystemStateMonitor:
    def __init__(self):
        self.repo_manager = EventRepositoryManager()
        self.first_run = True
        self.last_planner_run = None
        self.planner_running = False


    def repo_changed_since_last_run(self) -> bool:
        """
        Checks whether any repository category has been updated since the last auto planner run.
        Leverages the get_last_altered_by_data_type() method.
        """
        if self.last_planner_run is None:
            self.last_planner_run = datetime.now(timezone.utc) - timedelta(days=1)
        try:
            last_altered = self.repo_manager.get_last_altered_by_data_type()
            for category, altered_time in last_altered.items():
                if altered_time and altered_time > self.last_planner_run:
                    logger.info("Category '%s' was updated at %s", category, altered_time)
                    return True
            return False
        except Exception as e:
            logger.error("Error checking repo changes: %s", e)
            return False

    def get_system_state_summary(self) -> dict:
        """
        Returns the current (pruned) system state for each category.
        """
        state = {}
        try:
            state["last_run"] = f"{self.last_planner_run}"
            # For calendar: fetch all calendar events and prune those in the range [today, today+7]
            calendar_raw = json.loads(self.repo_manager.search_events("calendar"))
            state["calendar"] = prune_calendar_events(calendar_raw)

            # For email: get today's emails (pruned)
            email_raw = json.loads(self.repo_manager.search_events("email"))
            state["email"] = prune_email_events(email_raw)

            # For todo_task: get non-completed todos
            todo_raw = json.loads(self.repo_manager.search_events("todo_task"))
            state["todo_task"] = prune_todo_events(todo_raw)

            # For scheduler: we use the filtering and summarization functions.
            today_local = utc_to_local(datetime.now(timezone.utc)).date()
            scheduler_raw = filter_scheduler_events(cutoff_date=today_local)
            summarized_repeating_events = summarize_repeating_events(scheduler_raw)
            summarized_repeating_events = prune_scheduler_events(summarized_repeating_events)
            summarize_event_str = json.dumps(summarized_repeating_events)
            state["scheduler"] = summarize_event_str

        except Exception as e:
            logger.error("Error assembling system state summary: %s", e)
        return state

    def get_one_new_unified_item(self) -> dict:
        """
        Get one new UnifiedItem for processing.
        Returns empty dict if no new items available.
        
        Returns:
            Dict with structure: {source_type: [formatted_item]}
        """
        try:
            unified_manager = UnifiedItemManager()
            items = unified_manager.get_items_for_triage(limit=1)
            
            if not items:
                return {}
            
            item = items[0]
            source_type = item.source_type
            
            # Format the item based on source type
            formatted_item = self._format_unified_item(item)
            
            # Return in the format expected by auto_planner (similar to old get_new_events_since_last_run)
            return {source_type: [formatted_item]}
            
        except Exception as e:
            logger.error(f"Error getting new UnifiedItem: {e}", exc_info=True)
            return {}
    
    def _format_unified_item(self, item) -> dict:
        """
        Format a UnifiedItem into the format expected by auto_planner.
        """
        source_type = item.source_type
        data = item.data or {}
        
        if source_type == 'email':
            return {
                "subject": item.title or data.get('subject', 'No Subject'),
                "from": data.get('from', ''),
                "date": item.source_timestamp.isoformat() if item.source_timestamp else '',
                "importance": item.importance,
                "summary": item.content or data.get('summary', ''),
                "uid": data.get('uid', '')
            }
        elif source_type == 'calendar':
            return {
                "summary": item.title or data.get('summary', 'No Title'),
                "start": data.get('start', {}).get('dateTime', '') if isinstance(data.get('start'), dict) else data.get('start', ''),
                "end": data.get('end', {}).get('dateTime', '') if isinstance(data.get('end'), dict) else data.get('end', ''),
                "location": data.get('location', ''),
                "description": item.content or data.get('description', ''),
                "id": data.get('id', '')
            }
        elif source_type == 'todo_task':
            return {
                "title": item.title or data.get('title', 'No Title'),
                "due": data.get('due', ''),
                "status": data.get('status', 'needsAction'),
                "priority": data.get('priority', ''),
                "id": data.get('id', '')
            }
        else:
            # Fallback for unknown types
            return {
                "title": item.title or 'Unknown',
                "content": item.content or '',
                "source_type": source_type,
                "id": data.get('id', '')
            }

    def get_already_done_today(self) -> list:
        """
        Retrieves a list of actions (logs) recorded today to avoid duplication.
        Adds relative time context (e.g., "5 minutes ago") for better temporal understanding.
        """
        from app.assistant.utils.time_utils import get_local_time
        
        local_now = get_local_time()  # Get timezone-aware local time
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

        start_utc = local_midnight.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)

        session = get_session()
        try:
            logs = session.query(AgentActivityLog) \
                .filter(AgentActivityLog.timestamp >= start_utc) \
                .filter(AgentActivityLog.timestamp <= now_utc) \
                .all()
            
            results = []
            for log in logs:
                # Calculate time elapsed since this action
                # Ensure log.timestamp is timezone-aware (SQLite stores naive datetimes)
                log_timestamp = log.timestamp
                if log_timestamp.tzinfo is None:
                    log_timestamp = log_timestamp.replace(tzinfo=timezone.utc)
                time_diff = now_utc - log_timestamp
                
                # Format relative time
                if time_diff.total_seconds() < 120:  # Less than 2 minutes
                    relative_time = "just now"
                elif time_diff.total_seconds() < 3600:  # Less than 1 hour
                    minutes = int(time_diff.total_seconds() / 60)
                    relative_time = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
                elif time_diff.total_seconds() < 86400:  # Less than 1 day
                    hours = int(time_diff.total_seconds() / 3600)
                    relative_time = f"{hours} hour{'s' if hours != 1 else ''} ago"
                else:
                    days = int(time_diff.days)
                    relative_time = f"{days} day{'s' if days != 1 else ''} ago"
                
                results.append({
                    "timestamp": log_timestamp.isoformat(),
                    "time_ago": relative_time,
                    "agent": log.agent_name,
                    "description": log.description,
                    "status": log.status,
                    "notes": log.notes
                })
            
            return results
        except Exception as e:
            logger.error("Error fetching today's actions: %s", e)
            return []
        finally:
            session.close()

    def call_auto_planner_decider(self, new_info: dict, already_done: list, current_state: dict) -> dict:
        """
        Call the action_decider agent with the new UnifiedItem and current system state.
        
        Returns:
            Dict with keys: relevance_analysis, cost_benefit_analysis, decision, recommendation
        """
        try:
            from app.assistant.utils.time_utils import get_local_time_str
            
            # DEBUG: Log what we're receiving
            logger.info(f"=== call_auto_planner_decider DEBUG ===")
            logger.info(f"new_info type: {type(new_info)}, keys: {list(new_info.keys()) if isinstance(new_info, dict) else 'N/A'}, empty: {not new_info}")
            logger.info(f"already_done type: {type(already_done)}, length: {len(already_done) if isinstance(already_done, list) else 'N/A'}, empty: {not already_done}")
            logger.info(f"current_state type: {type(current_state)}, keys: {list(current_state.keys()) if isinstance(current_state, dict) else 'N/A'}, empty: {not current_state}")
            
            # Format new_info for the prompt - it's a dict with one source_type key containing a list
            # Extract the first item from the list for display
            new_info_str = ""
            if new_info:
                for source_type, items in new_info.items():
                    if items:
                        item = items[0]
                        new_info_str = json.dumps(item, indent=2)
                        logger.info(f"Formatted new_info from {source_type}: {new_info_str[:200]}...")
                        break
            else:
                logger.warning("new_info is EMPTY!")
            
            # Format current_state for the prompt
            current_state_str = json.dumps(current_state, indent=2) if current_state else ""
            if not current_state_str:
                logger.warning("current_state is EMPTY!")
            
            # Format already_done for the prompt
            already_done_str = json.dumps(already_done, indent=2) if already_done else ""
            if not already_done_str:
                logger.info("already_done is empty (expected on first run)")
            
            # Prepare input data matching the user.j2 template
            date_time = get_local_time_str()
            last_planner_run_str = utc_to_local(self.last_planner_run).strftime("%Y-%m-%d %H:%M:%S") if self.last_planner_run else "Never"
            
            input_data = {
                "date_time": date_time,
                "last_planner_run": last_planner_run_str,
                "current_state": current_state_str,
                "already_done": already_done_str,
                "new_info": new_info_str
            }
            
            logger.info(f"input_data keys: {list(input_data.keys())}")
            logger.info(f"input_data['new_info'] length: {len(input_data['new_info'])}")
            logger.info(f"input_data['current_state'] length: {len(input_data['current_state'])}")
            logger.info(f"=== END DEBUG ===")

            auto_planner_decider = DI.agent_factory.create_agent('auto_planner::action_decider')
            result = auto_planner_decider.action_handler(Message(agent_input=input_data))
            
            # Extract the structured output - agent_form returns: relevance_analysis, cost_benefit_analysis, decision, recommendation
            if result and hasattr(result, 'data'):
                output = result.data or {}
            else:
                output = result or {}
            
            return output
            
        except Exception as e:
            logger.error("Error calling auto_planner_decider: %s", e, exc_info=True)
            return {
                "relevance_analysis": "",
                "cost_benefit_analysis": f"Error: {str(e)}",
                "decision": False,
                "recommendation": ""
            }

    def record_planner_output(self, planner_result: ToolResult) -> str:
        """
        Records actions from the planner output into the AgentActivityLog.
        Expects each action to have: timestamp, agent, description, status, and optionally notes and parameters.
        
        Returns:
            The ID of the created log entry (for linking to UnifiedItem)
        """
        if not planner_result:
            return None

        session = get_session()
        try:
            data = planner_result.data
            task = data.get('task')
            status = data.get('status')
            what_was_done = data.get('what_was_done')
            log_id = str(uuid.uuid4())
            log = AgentActivityLog(
                id=log_id,
                timestamp=datetime.now(timezone.utc),
                agent_name="auto_planner",
                description=task,
                status=status,
                notes=what_was_done,
            )
            session.add(log)
            session.commit()
            return log_id
        except Exception as e:
            session.rollback()
            logger.error("Error recording planner output: %s", e)
            return None
        finally:
            session.close()

    def _process_recurring_events(self):
        """
        Simple flow:
        1. Check for new recurring calendar events that need user classification
        2. Ask user how to handle them (process_new_recurring_events)
        3. Once that's done, ingest everything else from the repo (emails, todos, schedulers, non-recurring calendar)
        """
        try:
            unified_manager = UnifiedItemManager()
            
            # Step 1: Process recurring events first (ask user, create rules, create UnifiedItems for NORMAL/CUSTOM)
            logger.info("🔄 Processing recurring calendar events...")
            recurring_result = process_new_recurring_events(max_events=3)
            
            rules_created = recurring_result.get('rules_created', 0)
            unified_items_created = recurring_result.get('unified_items_created', 0)
            
            if rules_created > 0:
                logger.info(f"✅ Created {rules_created} rules for recurring events, created {unified_items_created} UnifiedItems")
            
            # Step 2: Now ingest everything else from the repo (emails, todos, non-recurring calendar)
            # Note: Scheduler events fire directly and don't need UnifiedItems
            logger.info("📥 Ingesting all events from EventRepository into UnifiedItems...")
            ingest_result = unified_manager.ingest_all_sources()
            
            total_ingested = sum(len(items) for items in ingest_result.values())
            if total_ingested > 0:
                email_count = len(ingest_result.get('email', []))
                todo_count = len(ingest_result.get('todo_task', []))
                calendar_count = len(ingest_result.get('calendar', []))
                logger.info(f"📥 Ingested {total_ingested} new events: {email_count} email, {todo_count} todo, {calendar_count} calendar")
            
        except Exception as e:
            logger.error(f"Error in _process_recurring_events: {e}", exc_info=True)
            # Don't let this error break the auto_planner flow

    def run(self):
        from app.assistant.user_settings_manager.user_settings import is_feature_enabled
        
        # Check if auto_planner feature is enabled
        if not is_feature_enabled('auto_planner'):
            logger.debug("⏸️ Auto planner disabled in settings - skipping")
            return

        supervisor = DI.agent_factory.create_agent('auto_planner::supervisor')
        logger.info("Running system_state_monitor at %s", datetime.now(timezone.utc).isoformat())

        if self.planner_running:
            logger.info("Planner still running — skipping this cycle.")
            return

        self.planner_running = True
        try:
            # Check for new recurring calendar events that need user rules
            self._process_recurring_events()
            
            # Early exit: Check if there are any UnifiedItems to process before doing any work
            unified_manager = UnifiedItemManager()
            items_available = unified_manager.get_items_for_triage(limit=1)
            
            if not items_available:
                logger.info("No new UnifiedItems available for processing. Exiting early.")
                return
            
            # Get one new UnifiedItem for processing
            new_item = self.get_one_new_unified_item()
            
            if not new_item:
                logger.info("No new UnifiedItems available for processing.")
                return
            
            if self.first_run:
                logger.info("First planner run — treating full system state as both current and new.")
                current_state = self.get_system_state_summary()
                new_info = new_item  # Still process the new item
                self.first_run = False
            else:
                current_state = self.get_system_state_summary()
                new_info = new_item  # Use the single UnifiedItem instead of EventRepository events

            already_done = self.get_already_done_today()
            self.last_planner_run = datetime.now(timezone.utc)
            
            # Get the UnifiedItem that will be processed (we already checked above, but get fresh query)
            items = unified_manager.get_items_for_triage(limit=1)
            
            if not items:
                logger.warning("No UnifiedItem found for processing despite get_one_new_unified_item returning data")
                return
            
            processed_item = items[0]
            
            # Call action_decider - returns: relevance_analysis, cost_benefit_analysis, decision (str), snooze_hours (optional), recommendation
            decider_result = self.call_auto_planner_decider(new_info, already_done, current_state)
            
            from app.assistant.unified_item_manager.unified_item import ItemState
            
            if not decider_result:
                logger.error("action_decider returned no result")
                return
            
            decision = decider_result.get('decision', 'dismiss')
            
            # Handle three-way decision: act_now, snooze, or dismiss
            if decision == 'dismiss':
                # No action needed - mark as DISMISSED
                logger.info(f"Dismissing {processed_item.source_type} item: {processed_item.title}")
                unified_manager.transition_state(
                    item_id=processed_item.id,
                    new_state=ItemState.DISMISSED,
                    agent_decision="No action needed",
                    agent_notes=f"Relevance: {decider_result.get('relevance_analysis', 'N/A')[:200]}\nCost/Benefit: {decider_result.get('cost_benefit_analysis', 'N/A')[:200]}\nRecommendation: {decider_result.get('recommendation', 'N/A')[:200]}"
                )
            
            elif decision == 'snooze':
                # Snooze for later - mark as SNOOZED
                snooze_hours = decider_result.get('snooze_hours', 24)
                snooze_until = datetime.now(timezone.utc) + timedelta(hours=snooze_hours)
                logger.info(f"Snoozing {processed_item.source_type} item '{processed_item.title}' for {snooze_hours} hours (until {snooze_until})")
                unified_manager.transition_state(
                    item_id=processed_item.id,
                    new_state=ItemState.SNOOZED,
                    snooze_until=snooze_until,
                    agent_decision=f"Snoozed for {snooze_hours} hours",
                    agent_notes=f"Relevance: {decider_result.get('relevance_analysis', 'N/A')[:200]}\nCost/Benefit: {decider_result.get('cost_benefit_analysis', 'N/A')[:200]}\nRecommendation: {decider_result.get('recommendation', 'N/A')[:200]}"
                )
            
            elif decision == 'act_now':
                # Action needed - mark as ACTION_PENDING and proceed to supervisor
                logger.info(f"Action needed for {processed_item.source_type} item: {processed_item.title}")
                unified_manager.transition_state(
                    item_id=processed_item.id,
                    new_state=ItemState.ACTION_PENDING,
                    agent_decision=decider_result.get('recommendation', 'Action needed'),
                    agent_notes=f"Relevance: {decider_result.get('relevance_analysis', 'N/A')[:200]}\nCost/Benefit: {decider_result.get('cost_benefit_analysis', 'N/A')[:200]}"
                )
                
                supervisor_input = {
                    'new_info': new_info,
                    'already_done': already_done,
                    'current_state': current_state,
                    'relevance_analysis': decider_result.get('relevance_analysis', ''),
                    'cost_benefit_analysis': decider_result.get('cost_benefit_analysis', ''),
                    'recommendation': decider_result.get('recommendation', '')
                }
                supervisor_result = supervisor.action_handler(Message(agent_input=supervisor_input)).data or {}

                # Handle supervisor's three-way decision: act_now, snooze, or dismiss
                supervisor_decision = supervisor_result.get("decision", "dismiss")
                
                if supervisor_decision == "act_now":
                    # Supervisor approved action - call the team
                    auto_planner_team = DI.multi_agent_manager_factory.create_manager("auto_planner_team_manager")

                    auto_planner_team_result = auto_planner_team.request_handler(Message(task=supervisor_result.get("action_input")))

                    if auto_planner_team_result:
                        # Mark as ACTION_TAKEN after auto_planner completes successfully
                        action_log_id = self.record_planner_output(auto_planner_team_result)
                        unified_manager.transition_state(
                            item_id=processed_item.id,
                            new_state=ItemState.ACTION_TAKEN,
                            agent_decision="Action completed by auto_planner_team",
                            related_action_id=action_log_id
                        )
                        
                        # Send notification to UI feed (same as emi_team_manager does)
                        tool_message = ToolMessage(
                            tool_name="auto_planner_team",
                            sender="auto_planner_team",
                            receiver="emi_result_handler",
                            content=auto_planner_team_result.content,
                            tool_result=auto_planner_team_result,
                            tool_data={},
                            notification=True  # Mark as notification so it doesn't wait for user response
                        )
                        tool_message.event_topic = "emi_result_request"
                        DI.event_hub.publish(tool_message)
                        logger.info("Sent auto_planner result to UI feed")
                    else:
                        # Action attempted but failed
                        unified_manager.transition_state(
                            item_id=processed_item.id,
                            new_state=ItemState.FAILED,
                            agent_decision="Action attempted but failed",
                            agent_notes="auto_planner_team returned no result"
                        )
                
                elif supervisor_decision == "snooze":
                    # Supervisor wants to snooze - override decider's decision
                    snooze_hours = supervisor_result.get('snooze_hours', 24)
                    snooze_until = datetime.now(timezone.utc) + timedelta(hours=snooze_hours)
                    logger.info(f"Supervisor snoozed {processed_item.source_type} item '{processed_item.title}' for {snooze_hours} hours")
                    unified_manager.transition_state(
                        item_id=processed_item.id,
                        new_state=ItemState.SNOOZED,
                        snooze_until=snooze_until,
                        agent_decision=f"Supervisor snoozed for {snooze_hours} hours",
                        agent_notes=f"Supervisor reasoning: {supervisor_result.get('cost_benefit_analysis', 'N/A')[:300]}"
                    )
                
                else:  # dismiss
                    # Supervisor declined - mark as DISMISSED
                    unified_manager.transition_state(
                        item_id=processed_item.id,
                        new_state=ItemState.DISMISSED,
                        agent_decision="Supervisor declined action",
                        agent_notes=f"Action was recommended but supervisor declined: {supervisor_result.get('cost_benefit_analysis', 'N/A')[:300]}"
                    )


        finally:
            self.planner_running = False


# For testing the system state monitor independently.
if __name__ == "__main__":
    monitor = SystemStateMonitor()
    monitor.run()
