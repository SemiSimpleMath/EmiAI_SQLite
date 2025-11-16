"""
RAG Entry Generator Agent
Converts KG node-edge-node relationships into optimized RAG entries
"""

from typing import Dict, Any, List
from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.pydantic_classes import Message, ToolResult
from app.assistant.utils.logging_config import get_logger
import json

logger = get_logger(__name__)


class RAGEntryGenerator(Agent):
    """
    Agent that converts KG relationships into high-quality RAG entries
    """
    
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)
    
    def generate_rag_entry(self, relationship: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a RAG entry from a KG relationship
        """
        try:
            # Create a message for the agent to process
            message = Message(
                data_type="rag_generation",
                sender="KGRAGPipeline",
                receiver=self.name,
                content="Generate RAG entry from KG relationship",
                agent_input=relationship
            )
            
            result = self.action_handler(message)
            return result.data if result else None
            
        except Exception as e:
            logger.error(f"Error generating RAG entry: {e}")
            return None
    
    def process_llm_result(self, result):
        """
        Process the LLM result to extract RAG entry components
        """
        try:
            # Parse the structured output
            if isinstance(result, dict):
                rag_entry = {
                    'key': result.get('key', ''),
                    'text': result.get('text', ''),
                    'metadata': result.get('metadata', {}),
                    'relationship_id': result.get('relationship_id', ''),
                    'confidence': result.get('confidence', 0.8)
                }
            else:
                # Fallback for non-structured output
                rag_entry = {
                    'key': 'kg_relationship',
                    'text': str(result),
                    'metadata': {},
                    'relationship_id': '',
                    'confidence': 0.5
                }
            
            return ToolResult(
                result_type="rag_entry",
                content="RAG entry generated successfully",
                data_list=[rag_entry],
                data=rag_entry
            )
            
        except Exception as e:
            logger.error(f"Error processing LLM result: {e}")
            return ToolResult(
                result_type="error",
                content=f"Error processing result: {e}",
                data_list=[]
            )
    
    def get_system_prompt(self, message=None):
        """
        System prompt for RAG entry generation
        """
        return """
You are a RAG Entry Generator specialized in converting Knowledge Graph relationships into high-quality RAG (Retrieval-Augmented Generation) entries.

Your task is to take a node-edge-node relationship from a knowledge graph and create:
1. A SEMANTIC KEY that will be used for vector embedding and retrieval
2. A NATURAL TEXT that describes the relationship in a human-readable format
3. METADATA that provides additional context for the relationship

## Input Format:
You will receive a relationship object with:
- source_node: {label, description, aliases, type}
- target_node: {label, description, aliases, type}  
- edge: {type, attributes, context, created_at, updated_at}

## Output Requirements:

### SEMANTIC KEY:
- Should be a concise, searchable phrase that captures the essence of the relationship
- Include key entities and the relationship type
- Examples: "Jukka attended Berkeley", "Tesla electric vehicles", "Python programming language"

### NATURAL TEXT:
- Should be a natural, informative sentence that describes the relationship
- Include relevant context from edge attributes and node descriptions
- Make it human-readable and informative
- Examples: "Jukka attended the University of California, Berkeley from 1993 to 1997, where he majored in mathematics and physics and received a Bachelor of Science degree in both fields."

### METADATA:
- Include relevant timestamps, confidence scores, source information
- Preserve important attributes from the original relationship
- Add any additional context that might be useful for retrieval

## Guidelines:
- Prioritize clarity and informativeness in the natural text
- Make the semantic key specific enough for accurate retrieval
- Preserve important temporal and contextual information
- Handle cases where edge context provides rich additional details
- Ensure the output is suitable for both semantic search and human reading
"""

    def get_user_prompt(self, message=None):
        """
        User prompt that includes the relationship data
        """
        if not message or not message.agent_input:
            return "No relationship data provided"
        
        relationship = message.agent_input
        
        # Format the relationship data for the prompt
        source = relationship.get('source_node', {})
        target = relationship.get('target_node', {})
        edge = relationship.get('edge', {})
        
        prompt = f"""
Please generate a RAG entry for the following Knowledge Graph relationship:

SOURCE NODE:
- Label: {source.get('label', 'Unknown')}
- Type: {source.get('type', 'Unknown')}
- Description: {source.get('description', 'No description')}
- Aliases: {', '.join(source.get('aliases', []))}

TARGET NODE:
- Label: {target.get('label', 'Unknown')}
- Type: {target.get('type', 'Unknown')}
- Description: {target.get('description', 'No description')}
- Aliases: {', '.join(target.get('aliases', []))}

RELATIONSHIP:
- Type: {edge.get('type', 'Unknown')}
- Context: {edge.get('context', 'No additional context')}
- Attributes: {json.dumps(edge.get('attributes', {}), indent=2)}
- Created: {edge.get('created_at', 'Unknown')}
- Updated: {edge.get('updated_at', 'Unknown')}

Please generate:
1. A semantic key for vector embedding
2. Natural text describing this relationship
3. Relevant metadata

Focus on creating a comprehensive, informative description that captures all the important details from the relationship.
"""
        
        return prompt
