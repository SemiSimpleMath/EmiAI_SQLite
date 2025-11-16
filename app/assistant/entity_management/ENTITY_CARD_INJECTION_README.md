# Entity Card Injection System

## Overview

The Entity Card Injection System replaces the previous RAG (Retrieval-Augmented Generation) system with a more targeted approach that injects relevant entity cards when specific entities are mentioned in conversations or team calls.

## Key Features

### 🎯 **Smart Entity Detection**
- **Pattern Matching**: Detects capitalized names and phrases that could be entities
- **Noise Filtering**: Excludes common words and short names that aren't entities
- **Context-Aware**: Different injection strategies for chat vs team calls

### 🔄 **Duplicate Prevention**
- **Chat History Tracking**: Checks if entity cards were already injected in the conversation
- **Session Management**: Prevents redundant injections within the same chat session
- **Global Blackboard Integration**: Uses the global blackboard to track injection history

### 📍 **Two Injection Points**

#### 1. **User Chat Injection**
- **Location**: `EmiAgent` and `EmiAudioAgent` message processing
- **Trigger**: When user mentions entities like "Katy", "Seija", "Microsoft"
- **Behavior**: Injects entity cards at the beginning of the message with clear separation
- **Duplicate Check**: Ensures entity cards aren't re-injected if already present in chat history

#### 2. **Team Call Injection**
- **Location**: `EmiTeamSelectorToolCaller` when calling other teams
- **Trigger**: When team calls contain entity names in task descriptions
- **Behavior**: Injects entity cards more subtly at the end of team messages
- **Scope**: Enhances task, information, content, and other relevant fields

## Architecture

### Core Components

#### **EntityCardInjector** (`app/assistant/utils/entity_card_injector.py`)
```python
class EntityCardInjector:
    def detect_entities_in_text(self, text: str) -> List[str]
    def get_entity_card_content(self, entity_name: str) -> Optional[str]
    def check_if_entity_injected_in_history(self, entity_name: str) -> bool
    def inject_entity_cards_into_text(self, text: str, context_type: str) -> Tuple[str, List[str]]
    def inject_into_team_call(self, message: Message) -> Message
```

#### **Integration Points**
- **EmiAgent**: Enhanced with entity card injection in `emi_chat_request_handler()`
- **EmiAudioAgent**: Enhanced with entity card injection in `emi_chat_speaking_mode_request_handler()`
- **EmiTeamSelectorToolCaller**: Enhanced with entity card injection in `_enhance_tool_data_with_entity_cards()`

## Usage Examples

### Chat Injection Example
```
User Input: "I need to call Katy about the project"

Enhanced Input:
[Entity Context - Katy]:
ENTITY CARD: Katy
Type: person
Original Description: Jukka's wife and mother of Annika and Peter
Generated Summary: Katy is Jukka's wife and the mother of their children Annika and Peter...
Key Facts:
• Married to Jukka Virtanen
• Mother of Annika and Peter
• Lives in the family home
...

I need to call Katy about the project
```

### Team Call Injection Example
```
Original Team Call:
Task: Contact Katy about project timeline
Information: Need to coordinate with Seija

Enhanced Team Call:
Task: Contact Katy about project timeline
Information: Need to coordinate with Seija

[Entity: Katy]
ENTITY CARD: Katy
Type: person
...

[Entity: Seija]
ENTITY CARD: Seija
Type: person
...
```

## Configuration

### Agent Configs Updated
- **Removed**: `rag_fields` configuration from agent configs
- **Added**: Entity card injection is now automatic and doesn't require configuration
- **Maintained**: All other agent functionality remains unchanged

### Entity Card Database
- **Source**: Generated from Knowledge Graph nodes via entity card pipeline
- **Storage**: Stored in `entity_cards` table with structured format
- **Retrieval**: Fast lookup by entity name for injection

## Benefits Over RAG

### ✅ **Advantages**
1. **Targeted Context**: Only injects relevant entity information when entities are mentioned
2. **No Noise**: Avoids injecting irrelevant information from RAG database
3. **Structured Data**: Entity cards contain well-structured, curated information
4. **Duplicate Prevention**: Smart tracking prevents redundant injections
5. **Performance**: Faster than semantic search, no embedding calculations needed
6. **Predictable**: Entity cards are consistent and reliable

### 🔄 **Migration Strategy**
1. **Phase 1**: Implement entity card injection alongside existing RAG
2. **Phase 2**: Disable RAG in agent configs (✅ Complete)
3. **Phase 3**: Monitor and optimize entity card injection
4. **Phase 4**: Remove RAG code when confident in new system

## Testing

### Test Script
Run the test script to verify the system:
```bash
python app/assistant/utils/test_entity_card_injection.py
```

### Test Coverage
- ✅ Entity detection in text
- ✅ Entity card retrieval from database
- ✅ Entity injection into chat messages
- ✅ Entity injection into team calls
- ✅ Duplicate detection logic

## Monitoring and Debugging

### Logging
The system provides detailed logging:
```
INFO - Enhanced user input with entity cards: ['Katy', 'Seija']
INFO - Injected entity card for 'Katy' in chat context
INFO - Enhanced tool data field 'task' with entity cards: ['Microsoft']
```

### Metrics
- Number of entities detected per message
- Number of entity cards injected
- Duplicate injection prevention events
- Entity card retrieval success/failure rates

## Future Enhancements

### Potential Improvements
1. **Advanced Entity Detection**: Use NLP for better entity recognition
2. **Contextual Relevance**: Only inject entities that are contextually relevant
3. **Dynamic Updates**: Update entity cards based on new information
4. **User Preferences**: Allow users to control which entities get injected
5. **Performance Optimization**: Cache frequently accessed entity cards

### Integration Opportunities
1. **Knowledge Graph Updates**: Automatically update entity cards when KG changes
2. **Conversation Memory**: Use entity cards to enhance conversation memory
3. **Multi-Modal**: Extend to handle images, documents, and other media types

## Troubleshooting

### Common Issues

#### No Entity Cards Found
- **Cause**: Entity cards haven't been generated from Knowledge Graph
- **Solution**: Run the entity card pipeline: `python app/assistant/kg_rag_pipeline/kg_rag_pipeline.py`

#### Duplicate Injections
- **Cause**: Global blackboard not properly tracking injection history
- **Solution**: Check global blackboard initialization and message storage

#### Performance Issues
- **Cause**: Too many entity cards being injected
- **Solution**: Review entity detection patterns and filtering logic

### Debug Mode
Enable debug logging to see detailed injection process:
```python
logger.setLevel(logging.DEBUG)
```

## Conclusion

The Entity Card Injection System provides a more targeted, efficient, and reliable approach to context enhancement compared to the previous RAG system. By focusing on specific entities mentioned in conversations, it delivers relevant information without noise while maintaining the conversation flow.
