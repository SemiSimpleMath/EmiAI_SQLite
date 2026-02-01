"""
Entity Card Injection Service
Handles intelligent injection of entity cards into chat and team calls with duplicate detection
"""

from typing import List, Set, Optional, Tuple
from app.models.base import get_session
from app.assistant.entity_management.entity_cards import get_entity_card_for_prompt_injection
from app.assistant.entity_management.entity_catalog import get_entity_catalog
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class EntityCardInjector:
    """
    Service for injecting entity cards into chat and team calls with duplicate detection
    """
    
    def __init__(self):
        self.injected_entities: Set[str] = set()  # Track injected entities in current session
    
    def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize and normalize user text into a list of tokens used for matching.
        Rules:
        - Lowercase
        - Strip leading and trailing punctuation
        - Strip possessive 's or 's at the end of a token
        """
        if not text:
            return []
        tokens: List[str] = []
        # Work on lowercase
        lowered = text.lower()
        raw_tokens = lowered.split()

        print("JUKKA DEGBUG: ", text)

        for raw in raw_tokens:
            token = raw
            # Strip leading punctuation
            while token and not token[0].isalnum():
                token = token[1:]
            # Strip trailing punctuation except apostrophe
            while token and not token[-1].isalnum() and token[-1] not in ("'", "'"):
                token = token[:-1]
            if not token:
                continue
            # Handle possessive on the last characters
            if token.endswith("'s") or token.endswith("'s"):
                token = token[:-2]
            if token:
                tokens.append(token)
        return tokens

    def detect_entities_in_text(self, text: str) -> List[str]:
        """
        Detect entity names present in the given text using the preloaded EntityCatalog.
        Matching rules:
        - Exact match on normalized single tokens or multi word phrases
        - Case insensitive
        - Allow possessive for the last word (Jukka's -> Jukka)
        - Do not match inside larger words (RAG does not match Ragged)
        """
        if not text:
            return []

        catalog = get_entity_catalog()
        tokens = self._tokenize_text(text)
        if not tokens:
            return []

        found: Set[str] = set()

        # Single word matches
        for t in tokens:
            if t in catalog.single_word_index:
                found.update(catalog.single_word_index[t])

        # Multi word phrase matches
        n = len(tokens)
        if catalog.phrase_lengths:
            for i in range(n):
                for length in catalog.phrase_lengths:
                    if i + length > n:
                        continue
                    key = tuple(tokens[i : i + length])
                    entity_map = catalog.multi_word_index.get(length)
                    if not entity_map:
                        continue
                    canonical_names = entity_map.get(key)
                    if canonical_names:
                        found.update(canonical_names)

        # Return canonical entity names without duplicates
        result = sorted(found)
        if result:
            logger.info(f"🎯 Detected entities: {result}")
        return result

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
                if (
                    "entity_card_injection" in (getattr(msg, "sub_data_type", []) or [])
                    and hasattr(msg, 'metadata') and msg.metadata
                    and 'entity_name' in msg.metadata
                    and msg.metadata['entity_name'] == entity_name
                ):
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
            should_inject = self.should_inject_entity(entity_name, context_type)
            
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
