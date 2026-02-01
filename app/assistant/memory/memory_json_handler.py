"""
Memory JSON Handler

Executes structured operations on JSON resource files based on LLM decisions.
LLM provides semantic understanding, Python provides precision.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.path_utils import get_resources_dir
from app.assistant.utils.time_utils import utc_to_local

logger = get_logger(__name__)


class MemoryJsonHandler:
    """Handles structured memory operations on JSON resource files."""
    
    def __init__(self):
        self.resources_dir = get_resources_dir()
    
    def execute_edits(self, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute a list of JSON edits from json_editor agent.
        
        Args:
            edits: List of edit dicts with structure:
                {
                    "operation": "delete|update|insert|no_change",
                    "file": "resource_user_food_prefs.json",
                    "path": "food.likes[2]" or "food.likes",
                    "new_value": {...} (for insert/update),
                    "reason": "..."
                }
        
        Returns:
            Dict with success status and details
        """
        results = []
        
        for edit in edits:
            try:
                result = self._execute_single_edit(edit)
                results.append(result)
            except Exception as e:
                logger.error(f"Error executing edit: {e}", exc_info=True)
                results.append({
                    'success': False,
                    'operation': edit.get('operation'),
                    'error': str(e)
                })
        
        return {
            'success': all(r.get('success', False) for r in results),
            'edits_executed': len(results),
            'results': results
        }
    
    def execute_operations(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute a list of memory operations (OLD FORMAT - kept for compatibility).
        
        Args:
            operations: List of operation dicts with structure:
                {
                    "file": "resource_user_food_prefs.json",
                    "path": "food.likes",
                    "operation": "append|update|remove",
                    "value": {...} or search criteria
                }
        
        Returns:
            Dict with success status and details
        """
        results = []
        
        for op in operations:
            try:
                result = self._execute_single_operation(op)
                results.append(result)
            except Exception as e:
                logger.error(f"Error executing operation: {e}", exc_info=True)
                results.append({
                    'success': False,
                    'operation': op.get('operation'),
                    'error': str(e)
                })
        
        return {
            'success': all(r.get('success', False) for r in results),
            'operations_executed': len(results),
            'results': results
        }
    
    def _execute_single_edit(self, edit: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single edit from json_editor agent."""
        file_name = edit['file']
        path = edit['path']
        operation = edit['operation']
        
        # Load file
        file_path = self.resources_dir / file_name
        if not file_path.exists():
            return {
                'success': False,
                'operation': operation,
                'error': f"File not found: {file_name}"
            }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle no_change
        if operation == 'no_change':
            return {
                'success': True,
                'operation': 'no_change',
                'reason': edit.get('reason', 'No change needed')
            }
        
        # Parse path with array indices (e.g., "food.likes[2]")
        parent_data, target_key, target_index = self._parse_edit_path(data, path)
        
        if parent_data is None:
            return {
                'success': False,
                'operation': operation,
                'error': f"Path not found: {path}"
            }
        
        # Execute operation
        if operation == 'delete':
            result = self._edit_delete(parent_data, target_key, target_index, edit)
        elif operation == 'update':
            result = self._edit_update(parent_data, target_key, target_index, edit)
        elif operation == 'insert':
            result = self._edit_insert(parent_data, target_key, edit)
        else:
            return {
                'success': False,
                'operation': operation,
                'error': f"Unknown operation: {operation}"
            }
        
        # Save file only if a real change was made.
        # Some operations may be successful but no-op (e.g., skipped duplicates).
        changed = result.get("changed", True)
        if result.get('success') and changed:
            # Update metadata (use LOCAL time since resource files go to LLMs)
            if '_metadata' in data:
                now_local = utc_to_local(datetime.now(timezone.utc))
                data['_metadata']['last_updated'] = now_local.strftime('%Y-%m-%d')

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        result['file'] = file_name
        result['path'] = path
        return result
    
    def _parse_edit_path(self, data: Dict, path: str):
        """
        Parse path with array indices (e.g., 'food.likes[2]').
        
        Returns:
            (parent_data, target_key, target_index)
            - parent_data: The parent container (dict or list)
            - target_key: The key/field to access
            - target_index: Array index if path ends with [i], else None
        """
        import re
        
        # Check for array index at end
        array_match = re.match(r'^(.+)\[(\d+)\]$', path)
        if array_match:
            base_path = array_match.group(1)
            index = int(array_match.group(2))
            
            # Navigate to parent list
            parent = self._navigate_path(data, base_path)
            if parent is None or not isinstance(parent, list):
                return None, None, None
            
            return parent, None, index
        
        # No array index - navigate to parent dict
        parts = path.split('.')
        if len(parts) == 1:
            # Top-level key
            return data, parts[0], None
        
        parent_path = '.'.join(parts[:-1])
        target_key = parts[-1]
        
        parent = self._navigate_path(data, parent_path)
        if parent is None:
            return None, None, None
        
        return parent, target_key, None
    
    def _edit_delete(self, parent_data, target_key, target_index, edit):
        """Delete item from list or field from dict."""
        if target_index is not None:
            # Delete from list
            if target_index < len(parent_data):
                removed = parent_data.pop(target_index)
                return {
                    'success': True,
                    'operation': 'delete',
                    'action': 'removed',
                    'changed': True,
                    'item': str(removed)
                }
            else:
                return {
                    'success': False,
                    'operation': 'delete',
                    'error': f"Index {target_index} out of range"
                }
        else:
            # Delete from dict
            if isinstance(parent_data, dict) and target_key in parent_data:
                removed = parent_data.pop(target_key)
                return {
                    'success': True,
                    'operation': 'delete',
                    'action': 'removed',
                    'changed': True,
                    'field': target_key
                }
            else:
                return {
                    'success': False,
                    'operation': 'delete',
                    'error': f"Key '{target_key}' not found"
                }
    
    def _edit_update(self, parent_data, target_key, target_index, edit):
        """Update item in list or field in dict."""
        new_value = edit.get('new_value', {})

        # Support JSON-encoded strings from strict structured outputs.
        # If it's a string, try to decode JSON; fall back to raw string if not JSON.
        if isinstance(new_value, str):
            try:
                new_value = json.loads(new_value)
            except Exception as e:
                logger.debug(f"MemoryJsonHandler: new_value not valid JSON (keeping raw string): {e}", exc_info=True)
        
        if target_index is not None:
            # Update list item
            if target_index < len(parent_data):
                old_item = parent_data[target_index]
                if isinstance(old_item, dict) and isinstance(new_value, dict):
                    parent_data[target_index] = {**old_item, **new_value}
                else:
                    parent_data[target_index] = new_value
                return {
                    'success': True,
                    'operation': 'update',
                    'action': 'updated',
                    'changed': True,
                    'index': target_index
                }
            else:
                return {
                    'success': False,
                    'operation': 'update',
                    'error': f"Index {target_index} out of range"
                }
        else:
            # Update dict field
            if isinstance(parent_data, dict):
                if target_key in parent_data and isinstance(parent_data[target_key], dict) and isinstance(new_value, dict):
                    parent_data[target_key] = {**parent_data[target_key], **new_value}
                else:
                    parent_data[target_key] = new_value
                return {
                    'success': True,
                    'operation': 'update',
                    'action': 'updated',
                    'changed': True,
                    'field': target_key
                }
            else:
                return {
                    'success': False,
                    'operation': 'update',
                    'error': f"Cannot update {type(parent_data)}"
                }
    
    def _edit_insert(self, parent_data, target_key, edit):
        """Insert new item into list or dict."""
        new_value = edit.get('new_value', {})

        # Support JSON-encoded strings from strict structured outputs.
        if isinstance(new_value, str):
            try:
                new_value = json.loads(new_value)
            except Exception as e:
                logger.debug(f"MemoryJsonHandler: new_value not valid JSON (keeping raw string): {e}", exc_info=True)
        
        if isinstance(parent_data, list):
            # Skip duplicates for lists of dicts that use a stable `item` key.
            if isinstance(new_value, dict) and "item" in new_value:
                new_item_key = new_value.get("item")
                if any(
                    isinstance(existing, dict) and existing.get("item") == new_item_key
                    for existing in parent_data
                ):
                    return {
                        'success': True,
                        'operation': 'insert',
                        'action': 'skipped_duplicate',
                        'changed': False,
                        'item': str(new_value),
                    }

            # Add metadata for lists of dicts
            if isinstance(new_value, dict):
                if 'added' not in new_value:
                    # Use LOCAL time since resource files go to LLMs
                    now_local = utc_to_local(datetime.now(timezone.utc))
                    new_value['added'] = now_local.strftime('%Y-%m-%d')
            
            parent_data.append(new_value)
            return {
                'success': True,
                'operation': 'insert',
                'action': 'appended',
                'changed': True,
                'item': str(new_value)
            }
        elif isinstance(parent_data, dict):
            # Insert into dict
            if target_key:
                parent_data[target_key] = new_value
                return {
                    'success': True,
                    'operation': 'insert',
                    'action': 'added',
                    'changed': True,
                    'field': target_key
                }
            else:
                return {
                    'success': False,
                    'operation': 'insert',
                    'error': 'Target key required for dict insert'
                }
        else:
            return {
                'success': False,
                'operation': 'insert',
                'error': f"Cannot insert into {type(parent_data)}"
            }
    
    def _execute_single_operation(self, op: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single memory operation (OLD FORMAT)."""
        file_name = op['file']
        path = op['path']
        operation = op['operation']
        
        # Load file
        file_path = self.resources_dir / file_name
        if not file_path.exists():
            return {
                'success': False,
                'operation': operation,
                'error': f"File not found: {file_name}"
            }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Navigate to path
        target = self._navigate_path(data, path)
        if target is None:
            return {
                'success': False,
                'operation': operation,
                'error': f"Path not found: {path}"
            }
        
        # Execute operation
        if operation == 'append':
            result = self._op_append(target, op, path)
        elif operation == 'update':
            result = self._op_update(target, op, path)
        elif operation == 'remove':
            result = self._op_remove(target, op, path)
        elif operation == 'no_change':
            result = {
                'success': True,
                'operation': 'no_change',
                'reason': op.get('reason', 'No change needed')
            }
        else:
            return {
                'success': False,
                'operation': operation,
                'error': f"Unknown operation: {operation}"
            }
        
        # Save file if changes made
        if result.get('success') and operation != 'no_change':
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Update metadata (use LOCAL time since resource files go to LLMs)
            if '_metadata' in data:
                now_local = utc_to_local(datetime.now(timezone.utc))
                data['_metadata']['last_updated'] = now_local.strftime('%Y-%m-%d')
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        
        result['file'] = file_name
        result['path'] = path
        return result
    
    def _navigate_path(self, data: Dict, path: str) -> Any:
        """Navigate to a path in nested dict (e.g., 'food.likes')."""
        parts = path.split('.')
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        
        return current
    
    def _op_append(self, target: List, op: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Append operation: Add new item to list."""
        if not isinstance(target, list):
            return {
                'success': False,
                'operation': 'append',
                'error': f"Target is not a list: {type(target)}"
            }
        
        value = op['value']
        
        # Add metadata
        if isinstance(value, dict):
            if 'added' not in value:
                # Use LOCAL time since resource files go to LLMs
                now_local = utc_to_local(datetime.now(timezone.utc))
                value['added'] = now_local.strftime('%Y-%m-%d')
            if 'expiry' not in value:
                value['expiry'] = op.get('expiry', None)
        
        # Check for duplicates (by 'item' key if dict, or exact match if string)
        if isinstance(value, dict) and 'item' in value:
            if any(item.get('item') == value['item'] for item in target if isinstance(item, dict)):
                return {
                    'success': True,
                    'operation': 'append',
                    'action': 'skipped_duplicate',
                    'item': value.get('display', value.get('item'))
                }
        elif value in target:
            return {
                'success': True,
                'operation': 'append',
                'action': 'skipped_duplicate',
                'item': str(value)
            }
        
        # Append
        target.append(value)
        
        return {
            'success': True,
            'operation': 'append',
            'action': 'added',
            'item': value.get('display', value.get('item', str(value))) if isinstance(value, dict) else str(value)
        }
    
    def _op_update(self, target: Any, op: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Update operation: Modify existing item."""
        search = op.get('search', {})
        value = op['value']
        
        if isinstance(target, list):
            # Find item in list
            for i, item in enumerate(target):
                if self._matches(item, search):
                    target[i] = {**item, **value} if isinstance(item, dict) else value
                    return {
                        'success': True,
                        'operation': 'update',
                        'action': 'updated',
                        'item': str(item)
                    }
            
            return {
                'success': False,
                'operation': 'update',
                'error': 'Item not found'
            }
        
        elif isinstance(target, dict):
            # Update dict fields
            target.update(value)
            return {
                'success': True,
                'operation': 'update',
                'action': 'updated',
                'fields': list(value.keys())
            }
        
        return {
            'success': False,
            'operation': 'update',
            'error': f"Cannot update type: {type(target)}"
        }
    
    def _op_remove(self, target: List, op: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Remove operation: Delete item from list."""
        if not isinstance(target, list):
            return {
                'success': False,
                'operation': 'remove',
                'error': f"Target is not a list: {type(target)}"
            }
        
        search = op.get('search', {})
        
        # Find and remove
        for i, item in enumerate(target):
            if self._matches(item, search):
                removed = target.pop(i)
                return {
                    'success': True,
                    'operation': 'remove',
                    'action': 'removed',
                    'item': str(removed)
                }
        
        return {
            'success': False,
            'operation': 'remove',
            'error': 'Item not found'
        }
    
    def _matches(self, item: Any, search: Dict[str, Any]) -> bool:
        """Check if item matches search criteria."""
        if not search:
            return False
        
        if isinstance(item, dict):
            return all(item.get(k) == v for k, v in search.items())
        else:
            return item == search.get('value')


# Singleton
_handler = None

def get_memory_json_handler() -> MemoryJsonHandler:
    """Get the global MemoryJsonHandler instance."""
    global _handler
    if _handler is None:
        _handler = MemoryJsonHandler()
    return _handler

