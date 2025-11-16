"""
Recurring Event Questioner

Asks the user how to handle recurring calendar events when encountered for the first time.

Architecture:
- Uses dedicated `recurring_event_questioner_manager` multi-agent manager
- Manager has its own agent with calendar-specific prompts (not KG repair prompts)
- Agent uses `ask_user` tool to interact with user
- Similar pattern to kg_repair_pipeline's questioner, but separate manager
"""

from typing import Dict, Any, Optional
import json
from datetime import datetime, timezone
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger
from app.assistant.unified_item_manager.recurring_event_rules import (
    RecurringEventRuleManager,
    RecurringEventRuleAction
)

logger = get_logger(__name__)


class RecurringEventQuestioner:
    """
    Asks user about recurring calendar events and creates rules based on response.
    
    Uses the questioner_manager multi-agent pattern to interact with the user
    via the ask_user tool.
    """
    
    def __init__(self):
        """Initialize questioner"""
        self.multi_agent_factory = DI.multi_agent_manager_factory
        self.rule_manager = RecurringEventRuleManager()
    
    def ask_user_about_recurring_event(self, unified_item) -> Optional[Dict[str, Any]]:
        """
        Ask the user how to handle a recurring calendar event.
        
        Args:
            unified_item: UnifiedItem with recurring calendar event
            
        Returns:
            Dict with rule creation result, or None if failed
        """
        try:
            event_data = unified_item.data or {}
            item_metadata = unified_item.item_metadata or {}
            recurring_event_id = item_metadata.get('recurring_event_id')
            event_title = unified_item.title or "Unknown Event"
            
            logger.info(f"❓ Asking user about recurring event: {event_title}")
            print(f"   🔍 Debug: event_data type = {type(event_data)}, has {len(event_data)} keys")
            
            # Create recurring_event_questioner_manager
            questioner_manager = self.multi_agent_factory.create_manager("recurring_event_questioner_manager")
            
            # Prepare data dict - manager will unpack this to blackboard for agent access
            # Handle both nested dict format and flattened string format for start/end
            start_raw = event_data.get('start', '')
            end_raw = event_data.get('end', '')
            
            # If start/end are dicts, extract dateTime or date; if strings, use as-is
            if isinstance(start_raw, dict):
                start_time = start_raw.get('dateTime') or start_raw.get('date', '')
            else:
                start_time = start_raw or ''
                
            if isinstance(end_raw, dict):
                end_time = end_raw.get('dateTime') or end_raw.get('date', '')
            else:
                end_time = end_raw or ''
            
            # Handle recurrence_rule - can be a list or single string
            recurrence_rule = event_data.get('recurrence_rule') or event_data.get('recurrence')
            if isinstance(recurrence_rule, list):
                recurrence_rule_str = ', '.join(recurrence_rule)
            elif recurrence_rule:
                recurrence_rule_str = str(recurrence_rule)
            else:
                recurrence_rule_str = ''
            
            data = {
                "event_title": event_title,
                "recurring_event_id": recurring_event_id,
                "event_description": event_data.get('description', ''),
                "recurrence_rule": recurrence_rule_str,
                "start_time": start_time,
                "end_time": end_time,
                "calendar": event_data.get('calendar_name', '')
            }
            
            print(f"   📋 Event data being passed to manager:")
            print(f"      event_title: {data['event_title']}")
            print(f"      recurrence_rule: {data['recurrence_rule']}")
            print(f"      calendar: {data['calendar']}")
            
            message = Message(
                data_type="agent_activation",
                sender="recurring_event_questioner",
                receiver="recurring_event_questioner_manager",
                content=f"Ask user how to handle this recurring calendar event",
                task=f"Ask user how to handle recurring event: {event_title}",
                data=data  # Manager unpacks this to blackboard automatically
            )
            
            # Execute via manager
            print("   └─ Sending message to agent...\n")
            result = questioner_manager.request_handler(message)
            
            if not result:
                logger.error(f"❌ questioner_manager returned no result for event {event_title}")
                print("   ❌ Manager returned no result")
                return None
            
            print(f"\n📤 AGENT OUTPUT:")
            print(f"   Result type: {type(result)}")
            print(f"   Result data: {result.data if hasattr(result, 'data') else result}")
            
            # Parse user response and create rule
            print(f"\n🔧 Parsing agent output and creating rule...")
            rule_result = self._parse_response_and_create_rule(
                result,
                recurring_event_id,
                event_title
            )
            
            logger.info(f"✅ Created rule for recurring event: {event_title} -> {rule_result.get('action')}")
            return rule_result
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to ask user about recurring event: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            print(f"   ❌ Exception details: {e}")
            print(f"   Full traceback:\n{traceback.format_exc()}")
            return None
    
    def _parse_response_and_create_rule(
        self,
        manager_result,
        recurring_event_id: str,
        event_title: str
    ) -> Dict[str, Any]:
        """
        Parse user response and create a recurring event rule.
        
        Args:
            manager_result: ToolResult from questioner_manager
            recurring_event_id: Google Calendar recurring_event_id
            event_title: Human-readable event title
            
        Returns:
            Dict with rule creation result
        """
        try:
            # Extract user response from manager result
            agent_output = manager_result.data if hasattr(manager_result, 'data') else None
            
            if not agent_output:
                logger.error(f"❌ No data in manager result for event {event_title}")
                print("   ❌ Agent failed to return output - cannot create rule")
                print("   This event will be skipped and retried on next run")
                return {
                    'success': False,
                    'error': 'Agent returned no output data - ask_user may have failed'
                }
            
            print(f"   📝 Raw agent_output: {agent_output}")
            logger.info(f"📝 Raw agent_output for {event_title}: {agent_output}")
            
            # The agent output might be at the top level OR nested under 'final_answer'
            # Check both locations
            if 'final_answer' in agent_output:
                final_answer = agent_output.get('final_answer', {})
            elif 'ignore' in agent_output or 'normal' in agent_output or 'custom_instructions' in agent_output:
                # Data is at top level - this is the final_answer structure
                final_answer = {
                    'ignore': agent_output.get('ignore'),
                    'normal': agent_output.get('normal'),
                    'custom_instructions': agent_output.get('custom_instructions')
                }
            else:
                final_answer = {}
            
            # Also check found_information for user's raw response (in case agent didn't parse correctly)
            found_information = agent_output.get('found_information', [])
            user_response_text = ' '.join(found_information) if found_information else ''
            
            print(f"   📝 Extracted final_answer: {final_answer}")
            print(f"   📝 User's raw response: {user_response_text}")
            logger.info(f"📝 Extracted final_answer for {event_title}: {final_answer}")
            logger.info(f"📝 User's raw response text: {user_response_text}")
            
            # If agent didn't parse correctly but we have user response, try to parse it ourselves
            if not final_answer.get('ignore') and not final_answer.get('normal') and not final_answer.get('custom_instructions'):
                if user_response_text:
                    logger.warning(f"⚠️ Agent didn't parse final_answer correctly, attempting fallback parsing from user text")
                    user_response_lower = user_response_text.lower()
                    # Check for ignore keywords
                    if any(keyword in user_response_lower for keyword in ['ignore', 'dismiss', 'skip', 'don\'t', 'dont', 'no']):
                        logger.info(f"✅ Fallback parsing: detected IGNORE from user text")
                        final_answer['ignore'] = True
                    # Check for normal keywords  
                    elif any(keyword in user_response_lower for keyword in ['normal', 'regular', 'keep', 'yes', 'ok']):
                        logger.info(f"✅ Fallback parsing: detected NORMAL from user text")
                        final_answer['normal'] = True
                    else:
                        logger.warning(f"⚠️ Could not parse user response into ignore/normal/custom")
            
            # Parse the final_answer to determine action
            print(f"   🔍 Parsing final_answer structure...")
            action, reason, custom_instructions = self._parse_final_answer(final_answer)
            print(f"   ➜ Determined action: {action}")
            
            # Create the rule
            print(f"   💾 Creating rule in recurring_event_rules table...")
            rule = self.rule_manager.create_rule(
                recurring_event_id=recurring_event_id,
                event_title=event_title,
                action=action,
                reason=reason,
                agent_instructions=custom_instructions
            )
            print(f"   ✅ Rule created (ID: {rule.id}, Action: {action})")
            
            return {
                'success': True,
                'action': action,
                'rule_id': rule.id,
                'reason': reason,
                'custom_instructions': custom_instructions
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to parse response and create rule: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_final_answer(self, final_answer: dict) -> tuple[str, str, Optional[str]]:
        """
        Parse final_answer from agent to determine action.
        
        Agent schema:
        - final_answer.normal: bool (if True, treat like non-recurring)
        - final_answer.ignore: bool (if True, always dismiss)
        - final_answer.custom_instructions: str (custom handling logic)
        
        Args:
            final_answer: Dict with 'normal', 'ignore', 'custom_instructions' keys
            
        Returns:
            (action, reason, custom_instructions)
        """
        ignore = final_answer.get('ignore')
        normal = final_answer.get('normal')
        custom_instructions = final_answer.get('custom_instructions')
        
        # Debug logging to see what we got
        logger.info(f"🔍 Parsing final_answer: ignore={ignore} (type: {type(ignore)}), normal={normal} (type: {type(normal)}), custom_instructions={custom_instructions}")
        print(f"   🔍 Parsing: ignore={ignore}, normal={normal}, custom={custom_instructions}")
        
        # Priority: ignore > normal > custom
        # Check explicitly for True (not just truthy) to catch None/False cases
        if ignore is True:
            return (
                RecurringEventRuleAction.IGNORE,
                "User requested to ignore this recurring event",
                None
            )
        
        if normal is True:
            return (
                RecurringEventRuleAction.NORMAL,
                "User requested to treat like normal (non-recurring) events",
                None
            )
        
        if custom_instructions and custom_instructions.strip():
            return (
                RecurringEventRuleAction.CUSTOM,
                "User provided custom handling instructions",
                custom_instructions
            )
        
        # No clear directive - this is an error, don't create a rule
        logger.error(f"❌ No clear action in final_answer - cannot create rule without user input")
        raise ValueError(
            "No clear directive in final_answer. Must have one of: ignore=True, normal=True, or custom_instructions. "
            "This indicates the agent failed to get a proper user response. Will retry on next cycle."
        )


# Standalone function for easy use in maintenance or other contexts
def process_new_recurring_event(unified_item) -> bool:
    """
    Process a new recurring calendar event by asking user and creating rule.
    
    Args:
        unified_item: UnifiedItem with recurring calendar event (state=NEW)
        

    Returns:
        True if rule was created, False otherwise
    """
    questioner = RecurringEventQuestioner()
    result = questioner.ask_user_about_recurring_event(unified_item)
    
    if result and result.get('success'):
        logger.info(f"✅ Rule created for recurring event: {unified_item.title}")
        
        # Apply the rule to the current instance
        recurring_event_id = unified_item.item_metadata.get('recurring_event_id')
        if recurring_event_id:
            rule_manager = RecurringEventRuleManager()
            rule_manager.apply_rule(recurring_event_id, unified_item)
        
        return True
    else:
        logger.error(f"❌ Failed to create rule for recurring event: {unified_item.title}")
        return False


if __name__ == "__main__":
    import app.assistant.tests.test_setup # This is just run for the import
    from app.assistant.ServiceLocator.service_locator import DI
    manager_registry = DI.manager_registry
    manager_registry.preload_all()
    process_new_recurring_event()


