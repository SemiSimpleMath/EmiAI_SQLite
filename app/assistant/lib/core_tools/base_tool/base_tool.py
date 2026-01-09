# File: app/assistant/lib/global_tools/base_tool.py

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.assistant.utils.pydantic_classes import ToolMessage, Message, ToolResult


class BaseTool(ABC):
    """
    Abstract base class for all tools.
    
    Tools that require user approval before execution should set:
        requires_approval = True
    
    When requires_approval=True, the tool will create an approval ticket
    unless the caller passes approval_granted=True (the "passkey").
    """
    name: str
    requires_approval: bool = False  # Override to True for sensitive tools

    def __init__(self, name: str):
        self.name = name

    def run(self, tool_message: 'ToolMessage') -> ToolResult:
        """
        Main entry point for tool execution. Handles approval flow.
        
        Callers should use this method, not execute() directly.
        """
        # Check if approval is needed
        if self.requires_approval:
            # Check for the "passkey" - approval_granted flag
            args = tool_message.tool_data.get('arguments', {})
            approval_granted = args.pop('approval_granted', False)  # Remove from args
            
            if not approval_granted:
                # Need approval - generate ticket
                return self._request_approval(tool_message)
        
        # Either no approval needed, or approval was granted - execute
        return self.execute(tool_message)

    @abstractmethod
    def execute(self, tool_message: 'ToolMessage') -> ToolResult:
        """
        Executes the tool. Override this in subclasses.
        
        Note: This is called AFTER approval check passes.

        Parameters:
        - tool_message (ToolMessage): The message triggering the tool execution.

        Returns:
        - ToolResult: The result of the tool execution.
        """
        pass
    
    def get_approval_message(self, tool_message: 'ToolMessage') -> tuple[str, str]:
        """
        Generate title and message for the approval popup.
        
        Override this to customize the approval prompt.
        Returns: (title, message)
        """
        args = tool_message.tool_data.get('arguments', {})
        args_preview = str(args)[:200]
        return (
            f"Allow {self.name}?",
            f"Arguments: {args_preview}"
        )
    
    def _request_approval(self, tool_message: 'ToolMessage') -> ToolResult:
        """
        Request user approval and BLOCK until user responds.
        
        Creates a ticket and polls until user accepts or rejects.
        Returns the actual tool result (on accept) or error (on reject).
        """
        import time
        
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            
            ticket_manager = DI.proactive_ticket_manager
            if not ticket_manager:
                raise RuntimeError("ProactiveTicketManager not available")
            
            # Get customized title/message from the tool
            title, message = self.get_approval_message(tool_message)
            
            # Store the full tool_message data for replay after approval
            tool_data = tool_message.tool_data.copy() if tool_message.tool_data else {}
            
            now = datetime.now(timezone.utc)
            
            ticket = ticket_manager.create_ticket(
                suggestion_type='tool_approval',
                title=title,
                message=message,
                action_type=f'tool_{self.name}',
                action_params={
                    'tool_name': self.name,
                    'tool_data': tool_data,
                    'requested_at': now.isoformat()
                },
                trigger_context={
                    'source': f'tool:{self.name}',
                    'time': now.isoformat()
                },
                valid_hours=1  # 1 hour timeout for tool approvals
            )
            
            if not ticket:
                raise RuntimeError("Failed to create approval ticket")
            
            ticket_id = ticket['ticket_id']  # create_ticket returns a dict
            logger.info(f"[{self.name}] 🔐 Waiting for user approval - ticket {ticket_id}")
            
            # Poll for user response (blocking)
            max_wait_seconds = 300  # 5 minute timeout
            poll_interval = 1  # Check every second
            elapsed = 0
            
            while elapsed < max_wait_seconds:
                time.sleep(poll_interval)
                elapsed += poll_interval
                
                # Check ticket state
                current_ticket = ticket_manager.get_ticket_by_id(ticket_id)
                if not current_ticket:
                    logger.warning(f"[{self.name}] Ticket {ticket_id} disappeared")
                    return ToolResult(
                        result_type='error',
                        content=f"Approval ticket lost: {title}"
                    )
                
                state = current_ticket.state
                
                # User ACCEPTED - execute the tool
                if state == 'accepted':
                    logger.info(f"[{self.name}] ✅ User approved: {title}")
                    # Mark as executing
                    ticket_manager.mark_executing(ticket_id)
                    # Actually execute the tool
                    result = self.execute(tool_message)
                    # Mark completed
                    ticket_manager.mark_completed(ticket_id, execution_result=result.content[:100] if result.content else 'OK')
                    return result
                
                # User REJECTED/DISMISSED - return error
                if state in ('dismissed', 'rejected'):
                    logger.info(f"[{self.name}] ❌ User rejected: {title}")
                    return ToolResult(
                        result_type='error',
                        content=f"DENIED: User has explicitly rejected this tool use ({self.name}). You MUST abort this action immediately. Do NOT retry, ask for confirmation, or attempt workarounds. The user's decision is final.",
                        data_list=[{
                            'status': 'rejected',
                            'tool_name': self.name,
                            'ticket_id': ticket_id,
                            'user_decision': 'DENIED - DO NOT RETRY'
                        }]
                    )
                
                # Ticket expired or failed
                if state in ('expired', 'failed'):
                    logger.info(f"[{self.name}] ⏰ Approval expired: {title}")
                    return ToolResult(
                        result_type='error',
                        content=f"Approval timed out: {title}"
                    )
            
            # Timeout waiting for response
            logger.warning(f"[{self.name}] ⏰ Approval timeout after {max_wait_seconds}s")
            ticket_manager.mark_expired(ticket_id)
            return ToolResult(
                result_type='error',
                content=f"Approval timed out after {max_wait_seconds}s: {title}"
            )
            
        except Exception as e:
            logger.error(f"[{self.name}] Error in approval flow: {e}", exc_info=True)
            return ToolResult(
                result_type='error',
                content=f"Approval failed: {str(e)}"
            )
    
    @staticmethod
    def create_rejection_result(tool_name: str, title: str, ticket_id: str, reason: str = None) -> 'ToolResult':
        """
        Create a ToolResult for when user rejects a tool approval.
        
        Returns a standard error-type result so existing error handling works.
        """
        content = f"User REJECTED: {title}"
        if reason:
            content += f" (Reason: {reason})"
        
        return ToolResult(
            result_type='error',
            content=content,
            data_list=[{
                'status': 'rejected',
                'tool_name': tool_name,
                'ticket_id': ticket_id,
                'title': title,
                'reason': reason or 'User dismissed'
            }]
        )
