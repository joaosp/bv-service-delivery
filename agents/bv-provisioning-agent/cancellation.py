"""
Cancellation management for BV Provisioning Agent

This module provides centralized cancellation state management with support for:
- Operation state tracking (idle, running, cancellation_requested, cancelled)
- Cancellation tokens for cooperative cancellation
- Natural language intent detection
- Confirmation flow management
- Per-conversation state for Teams integration
"""

import asyncio
import threading
import re
from enum import Enum
from typing import Dict, Any, Optional
from contextvars import ContextVar


class OperationState(Enum):
    """States for tracking current operation"""
    IDLE = "idle"
    EXTRACTING_SALESFORCE = "extracting_salesforce"
    ANALYZING_DOCUMENTS = "analyzing_documents"
    PROVISIONING_BHIVE = "provisioning_bhive"
    GENERATING_CSV = "generating_csv"
    GENERATING_REPORT = "generating_report"


class CancellationRequestedError(Exception):
    """Raised when an operation is cancelled by user request"""
    pass


class CancellationManager:
    """
    Thread-safe cancellation state manager.

    Manages operation state, cancellation requests, and confirmation flow.
    Uses asyncio.Event for cooperative cancellation of async operations.
    """

    # Natural language phrases that indicate cancellation intent
    CANCEL_PHRASES = [
        r'\bcancel\b',
        r'\bstop\b',
        r'\babort\b',
        r'\bnever\s*mind\b',
        r'\bnevermind\b',
        r'\bquit\b',
        r'\bhalt\b',
        r'\bterminate\b',
        r'\bend\s+this\b',
        r'\bdon\'?t\s+continue\b',
        r'\bforget\s+it\b',
        r'\bcancel\s+(the\s+)?(request|operation|extraction|provisioning)\b',
        r'\bstop\s+(the\s+)?(request|operation|extraction|provisioning)\b',
    ]

    # Compiled regex patterns for efficiency
    _cancel_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in CANCEL_PHRASES]

    def __init__(self):
        """Initialize the cancellation manager"""
        self._state: OperationState = OperationState.IDLE
        self._cancellation_requested: bool = False
        self._pending_confirmation: bool = False
        self._current_opportunity_id: Optional[str] = None
        self._lock = threading.Lock()
        self._cancel_event: asyncio.Event = asyncio.Event()

    def detect_cancellation_intent(self, message: str) -> bool:
        """
        Detect natural language cancellation intent in user message.

        Args:
            message: User's message text

        Returns:
            True if message indicates cancellation intent
        """
        if not message:
            return False

        message_lower = message.lower().strip()

        # Check for exact /cancel command
        if message_lower == '/cancel':
            return True

        # Check against natural language patterns
        for pattern in self._cancel_patterns:
            if pattern.search(message):
                return True

        return False

    def is_operation_running(self) -> bool:
        """Check if an operation is currently running"""
        with self._lock:
            return self._state != OperationState.IDLE

    def is_cancelled(self) -> bool:
        """Check if cancellation has been confirmed"""
        with self._lock:
            return self._cancellation_requested and not self._pending_confirmation

    def is_pending_confirmation(self) -> bool:
        """Check if awaiting user confirmation for cancellation"""
        with self._lock:
            return self._pending_confirmation

    def get_current_state(self) -> OperationState:
        """Get the current operation state"""
        with self._lock:
            return self._state

    def get_opportunity_id(self) -> Optional[str]:
        """Get the opportunity ID being processed"""
        with self._lock:
            return self._current_opportunity_id

    def set_state(self, state: OperationState) -> None:
        """
        Set the current operation state.

        Args:
            state: New operation state
        """
        with self._lock:
            self._state = state
            # Reset cancellation state when returning to idle
            if state == OperationState.IDLE:
                self._cancellation_requested = False
                self._pending_confirmation = False
                self._cancel_event.clear()

    def set_opportunity_id(self, opp_id: Optional[str]) -> None:
        """
        Set the opportunity ID being processed.

        Args:
            opp_id: Opportunity ID or None
        """
        with self._lock:
            self._current_opportunity_id = opp_id

    def request_cancellation(self) -> Dict[str, Any]:
        """
        Request cancellation (triggers confirmation flow).

        Returns:
            Dict with status and message for user
        """
        with self._lock:
            if self._state == OperationState.IDLE:
                return {
                    "success": False,
                    "message": "No operation is currently running."
                }

            if self._pending_confirmation:
                return {
                    "success": True,
                    "pending": True,
                    "message": "Cancellation already requested. Please confirm with 'yes' or abort with 'no'."
                }

            self._pending_confirmation = True
            state_desc = self._get_state_description()

            return {
                "success": True,
                "pending": True,
                "current_operation": self._state.value,
                "opportunity_id": self._current_opportunity_id,
                "message": f"Are you sure you want to cancel? Currently: {state_desc}. "
                          f"Data downloaded so far will be preserved. "
                          f"Type 'yes' to confirm or 'no' to continue."
            }

    def confirm_cancellation(self) -> Dict[str, Any]:
        """
        Confirm and execute cancellation.

        Sets the cancellation event that async operations should check.

        Returns:
            Dict with status and message for user
        """
        with self._lock:
            self._cancellation_requested = True
            self._pending_confirmation = False
            self._cancel_event.set()  # Signal async operations to stop

            state_desc = self._get_state_description()
            message = f"Cancellation confirmed. Stopping: {state_desc}."

            # Add BHive warning if provisioning was in progress
            if self._state == OperationState.PROVISIONING_BHIVE:
                message += (" WARNING: BHive provisioning request was already sent. "
                          "The operation may have completed on the server side. "
                          "Please check the BHive admin console to verify account status.")
            else:
                message += " Downloaded data has been preserved."

            return {
                "success": True,
                "cancelled": True,
                "previous_operation": self._state.value,
                "opportunity_id": self._current_opportunity_id,
                "message": message,
                "bhive_warning": self._state == OperationState.PROVISIONING_BHIVE
            }

    def abort_cancellation(self) -> None:
        """Abort cancellation request (user said no)"""
        with self._lock:
            self._pending_confirmation = False
            self._cancellation_requested = False

    def get_cancellation_token(self) -> asyncio.Event:
        """
        Get the asyncio.Event for cooperative cancellation.

        Async operations should periodically check if this event is set.

        Returns:
            asyncio.Event that will be set when cancellation is confirmed
        """
        return self._cancel_event

    def reset(self) -> None:
        """Reset all state (use when starting a new operation)"""
        with self._lock:
            self._state = OperationState.IDLE
            self._cancellation_requested = False
            self._pending_confirmation = False
            self._current_opportunity_id = None
            self._cancel_event.clear()

    def _get_state_description(self) -> str:
        """Get human-readable description of current state"""
        descriptions = {
            OperationState.IDLE: "idle",
            OperationState.EXTRACTING_SALESFORCE: "extracting Salesforce data",
            OperationState.ANALYZING_DOCUMENTS: "analyzing documents",
            OperationState.PROVISIONING_BHIVE: "provisioning to BHive",
            OperationState.GENERATING_CSV: "generating CSV",
            OperationState.GENERATING_REPORT: "generating report",
        }
        return descriptions.get(self._state, self._state.value)


# Global cancellation manager for CLI and Autonomous modes
_global_manager = CancellationManager()

# Per-conversation managers for Teams (keyed by conversation_id)
_conversation_managers: Dict[str, CancellationManager] = {}
_conversation_managers_lock = threading.Lock()

# Context variable to track current conversation ID
_current_conversation_id: ContextVar[Optional[str]] = ContextVar('current_conversation_id', default=None)


def get_cancellation_manager() -> CancellationManager:
    """
    Get the appropriate cancellation manager for the current context.

    In Teams context (conversation_id set), returns per-conversation manager.
    Otherwise, returns the global manager for CLI/Autonomous modes.

    Returns:
        CancellationManager instance
    """
    conversation_id = _current_conversation_id.get()
    if conversation_id:
        return get_conversation_cancellation_manager(conversation_id)
    return _global_manager


def get_conversation_cancellation_manager(conversation_id: str) -> CancellationManager:
    """
    Get or create a cancellation manager for a specific Teams conversation.

    Args:
        conversation_id: Teams conversation ID

    Returns:
        CancellationManager for that conversation
    """
    with _conversation_managers_lock:
        if conversation_id not in _conversation_managers:
            _conversation_managers[conversation_id] = CancellationManager()
        return _conversation_managers[conversation_id]


def set_current_conversation_id(conversation_id: Optional[str]) -> None:
    """
    Set the current conversation ID for context-aware manager selection.

    Call this at the start of Teams message handling.

    Args:
        conversation_id: Teams conversation ID or None
    """
    _current_conversation_id.set(conversation_id)


def cleanup_conversation(conversation_id: str) -> None:
    """
    Clean up cancellation manager for a conversation.

    Call this when a conversation ends or times out.

    Args:
        conversation_id: Teams conversation ID
    """
    with _conversation_managers_lock:
        if conversation_id in _conversation_managers:
            del _conversation_managers[conversation_id]


# Convenience aliases for backward compatibility
cancellation_manager = _global_manager
