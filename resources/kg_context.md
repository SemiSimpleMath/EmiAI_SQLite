# Knowledge Graph Context

This knowledge graph tracks {{ user_profile.name }}'s life and his interactions with {{ system_names.ai_assistant_name }}, his personal AI assistant.

## Entity Replacement Rules
- Always replace `I`, `Me`, or `User` with `{{ user_profile.name }}`
- Always replace `Assistant` or `{{ system_names.ai_assistant_name }}` with `{{ system_names.ai_assistant_name }}`

## Extraction Guidelines
- Extract facts about {{ user_profile.name }}'s life, personality, relationships, goals, and personal history
- Do not extract {{ system_names.ai_assistant_name }} responses to assistant type requests
- Only infer information from what {{ user_profile.name }} has said directly
- From any long exchange (more than 3 sentences) extract only core information. Favor heavily summarizing.

## System Entities
- There is **exactly ONE {{ user_profile.name }} entity** and **exactly ONE {{ system_names.ai_assistant_name }} entity** in the entire graph
- If you see a new node matching "{{ user_profile.name }}" (the user) or "{{ system_names.ai_assistant_name }}" (the AI assistant), **ALWAYS merge with the existing node**

