"""
Entity Card Injection Service
Handles intelligent injection of entity cards into chat and team calls with duplicate detection
"""

import re
from typing import List, Set, Optional, Tuple
from app.models.base import get_session
from app.assistant.entity_management.entity_cards import get_entity_card_for_prompt_injection
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class EntityCardInjector:
    """
    Service for injecting entity cards into chat and team calls with duplicate detection
    """
    
    def __init__(self):
        self.injected_entities: Set[str] = set()  # Track injected entities in current session
        self.entity_name_pattern = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')  # Match capitalized names
    
    def detect_entities_in_text(self, text: str) -> List[str]:
        """
        Detect potential entity names in text using simple pattern matching
        Returns list of potential entity names found (including alias matches)
        """
        if not text:
            return []
        
        # Find all capitalized words/phrases that could be entity names
        potential_entities = self.entity_name_pattern.findall(text)
        
        # Filter out common words that shouldn't be entities
        common_words = {
            'I', 'You', 'The', 'This', 'That', 'What', 'When', 'Where', 'Why', 'How',
            'Yes', 'No', 'Please', 'Thank', 'Hello', 'Goodbye', 'Okay', 'Sure',
            'Today', 'Tomorrow', 'Yesterday', 'Now', 'Then', 'Here', 'There'
        }
        
        # Filter out common words and short names (likely not entities)
        entities = []
        for entity in potential_entities:
            if (entity not in common_words and 
                len(entity) > 2 and  # Avoid very short names
                not entity.lower() in ['the', 'and', 'or', 'but', 'for', 'with', 'from']):
                entities.append(entity)
        
        # Now check for alias matches and get the canonical entity names
        canonical_entities = []
        for entity in entities:
            canonical_name = self.find_entity_by_name_or_alias(entity)
            if canonical_name:
                canonical_entities.append(canonical_name)
        
        return list(set(canonical_entities))  # Remove duplicates
    
    def find_entity_by_name_or_alias(self, entity_name: str) -> Optional[str]:
        """
        Find the canonical entity name by checking both entity names and aliases
        Returns the canonical entity name if found, None otherwise
        """
        try:
            session = get_session()
            
            # First, try to get the entity card directly by name
            card_content = get_entity_card_for_prompt_injection(session, entity_name)
            if card_content:
                session.close()
                return entity_name  # Found by exact name
            
            # If not found by exact name, search for aliases
            from app.assistant.entity_management.entity_cards import search_entity_cards
            
            # Search for entity cards that might match this name as an alias
            matching_cards = search_entity_cards(session, entity_name, limit=10)
            
            for card in matching_cards:
                # Check if the entity name matches any of the aliases
                if card.aliases:
                    for alias in card.aliases:
                        if entity_name.lower() == alias.lower():
                            session.close()
                            return card.entity_name  # Return canonical name
                
                # Also check original aliases
                if card.original_aliases:
                    for alias in card.original_aliases:
                        if entity_name.lower() == alias.lower():
                            session.close()
                            return card.entity_name  # Return canonical name
            
            session.close()
            return None
            
        except Exception as e:
            import traceback
            logger.error(f"Error finding entity by name or alias '{entity_name}': {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def get_entity_card_content(self, entity_name: str) -> Optional[str]:
        """
        Get entity card content for injection if it exists
        """
        try:
            session = get_session()
            card_content = get_entity_card_for_prompt_injection(session, entity_name)
            session.close()
            return card_content
        except Exception as e:
            logger.error(f"Error getting entity card for '{entity_name}': {e}")
            return None
    
    def check_if_entity_injected_in_history(self, entity_name: str) -> bool:
        """
        Check if entity card has been injected in the current chat history
        Uses global blackboard to check message history
        """
        try:
            # Get all messages from global blackboard
            messages = DI.global_blackboard.get_messages()
            
            # Check for entity card injection messages using sub_data_type and metadata
            for msg in messages:
                if (msg.sub_data_type == "entity_card_injection" and 
                    hasattr(msg, 'metadata') and msg.metadata and 
                    'entity_name' in msg.metadata and 
                    msg.metadata['entity_name'] == entity_name):
                    return True
                
                # Fallback: check content for entity context format
                if (msg.content and 
                    f"[Entity Context - {entity_name}]" in msg.content):
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking entity injection history for '{entity_name}': {e}")
            return False
    
    def inject_entity_cards_into_text(self, text: str, context_type: str = "chat") -> Tuple[str, List[str]]:
        """
        Inject entity cards into text and return enhanced text + list of injected entities
        
        Args:
            text: Original text to enhance
            context_type: Type of context ("chat" or "team_call")
        
        Returns:
            Tuple of (enhanced_text, list_of_injected_entities)
        """
        if not text:
            return text, []
        
        # Detect potential entities in the text
        detected_entities = self.detect_entities_in_text(text)
        
        if not detected_entities:
            return text, []
        
        enhanced_text = text
        injected_entities = []
        
        for entity_name in detected_entities:
            # Check if we should inject this entity
            should_inject = self._should_inject_entity(entity_name, context_type)
            
            if should_inject:
                card_content = self.get_entity_card_content(entity_name)
                if card_content:
                    # Inject the entity card
                    enhanced_text = self._inject_entity_card(enhanced_text, entity_name, card_content, context_type)
                    injected_entities.append(entity_name)
                    logger.info(f"Injected entity card for '{entity_name}' in {context_type} context")
        
        return enhanced_text, injected_entities
    
    def should_inject_entity(self, entity_name: str, context_type: str) -> bool:
        """
        Determine if an entity should be injected based on various criteria
        """
        # Always check if entity card exists
        card_content = self.get_entity_card_content(entity_name)
        if not card_content:
            return False
        
        # For chat context, duplicate detection is now handled in the agents
        # by checking the blackboard for existing injection messages
        
        # For team calls, we can be more aggressive with injection
        # since teams might need context even if mentioned before
        
        return True
    
    def _inject_entity_card(self, text: str, entity_name: str, card_content: str, context_type: str) -> str:
        """
        Inject entity card content into the text
        """
        if context_type == "chat":
            # For chat, inject at the beginning with clear separation
            injection = f"\n\n[Entity Context - {entity_name}]:\n{card_content}\n\n"
            return injection + text
        else:
            # For team calls, inject more subtly
            injection = f"\n[Entity: {entity_name}]\n{card_content}\n"
            return text + injection
    
    def inject_into_team_call(self, message: 'Message') -> 'Message':
        """
        Inject entity cards into a team call message
        """
        if not message.content:
            return message
        
        enhanced_content, injected_entities = self.inject_entity_cards_into_text(
            message.content, context_type="team_call"
        )
        
        if injected_entities:
            # Create enhanced message
            enhanced_message = message.copy()
            enhanced_message.content = enhanced_content
            
            # Add entity information to the information field
            if hasattr(enhanced_message, 'information') and enhanced_message.information:
                enhanced_message.information += f"\n\n[Injected Entity Cards: {', '.join(injected_entities)}]"
            else:
                enhanced_message.information = f"[Injected Entity Cards: {', '.join(injected_entities)}]"
            
            logger.info(f"Injected {len(injected_entities)} entity cards into team call: {injected_entities}")
            return enhanced_message
        
        return message
    
    def reset_session_tracking(self):
        """
        Reset the session-level tracking of injected entities
        Useful for new chat sessions
        """
        self.injected_entities.clear()
        logger.info("Reset entity injection session tracking")


# Global instance
entity_card_injector = EntityCardInjector()
