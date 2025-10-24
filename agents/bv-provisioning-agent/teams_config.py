"""
Microsoft Teams Bot Configuration

Environment variables required:
- MICROSOFT_APP_ID: Azure Bot Service App ID
- MICROSOFT_APP_PASSWORD: Azure Bot Service App Password
- MICROSOFT_APP_TYPE: "MultiTenant" or "SingleTenant" (default: MultiTenant)
- MICROSOFT_APP_TENANTID: Tenant ID (required for SingleTenant)
- BOT_ENDPOINT_PORT: Port for bot server (default: 3978)
- BOT_ENDPOINT_HOST: Host for bot server (default: 0.0.0.0)
"""

import os
from typing import Optional

class TeamsConfig:
    """Configuration for Microsoft Teams Bot"""

    # Azure Bot Service credentials
    APP_ID: str = os.getenv("MICROSOFT_APP_ID", "")
    APP_PASSWORD: str = os.getenv("MICROSOFT_APP_PASSWORD", "")
    APP_TYPE: str = os.getenv("MICROSOFT_APP_TYPE", "MultiTenant")
    APP_TENANTID: str = os.getenv("MICROSOFT_APP_TENANTID", "")

    # Bot server configuration
    PORT: int = int(os.getenv("BOT_ENDPOINT_PORT", "3978"))
    HOST: str = os.getenv("BOT_ENDPOINT_HOST", "0.0.0.0")

    # Bot endpoint path
    MESSAGES_ENDPOINT: str = "/api/messages"

    # Teams-specific settings
    TYPING_INDICATOR_ENABLED: bool = True
    MAX_MESSAGE_LENGTH: int = 28000  # Teams character limit

    # Conversation settings
    CONVERSATION_HISTORY_ENABLED: bool = True
    MAX_HISTORY_MESSAGES: int = 20

    # Streaming settings
    STREAMING_ENABLED: bool = True
    STREAMING_TEXT_BUFFER_SIZE: int = 2000  # Send text chunks at this size

    # User feedback settings
    SHOW_PROCESSING_MESSAGE: bool = False  # Send immediate "Processing..." message
    SHOW_TOOL_NOTIFICATIONS: bool = False  # Send generic "Using tool: X..." messages (if False, rely on agent's reasoning)
    TYPING_BEFORE_TOOL_USE: bool = True  # Send typing indicator before each tool notification
    TYPING_HEARTBEAT_ENABLED: bool = True  # Resend typing indicator during long operations
    TYPING_HEARTBEAT_INTERVAL: int = 3  # Seconds of inactivity before sending typing indicator

    # Logging settings
    VERBOSE_LOGGING: bool = True  # Enable detailed stdout logging for developers

    # Size limits (to prevent buffer overflow)
    MAX_TOOL_OUTPUT_SIZE: int = 50000  # Max characters for tool stdout/outputs
    MAX_CONVERSATION_CONTEXT_SIZE: int = 50000  # Max characters for conversation history
    MAX_CONVERSATION_HISTORY_ITEMS: int = 5  # Number of messages to keep in history

    # File attachment settings
    AUTO_SEND_FILES: bool = True  # Automatically send queued files after agent completes
    MAX_FILE_SIZE_MB: int = 4  # Maximum file size for inline attachment (Teams limit ~4MB)

    # File delivery method configuration
    INLINE_TEXT_FILE_THRESHOLD: int = 20000  # Max chars to send as inline code block (CSV/MD/TXT)
    FILE_DELIVERY_METHOD: str = "auto"  # "auto" (smart routing), "inline" (text only), "consent" (FileConsentCard only)
    SUPPORTED_TEXT_EXTENSIONS: list = ['.csv', '.md', '.txt', '.log', '.json', '.yaml', '.yml']

    # Response timeout (seconds)
    AGENT_TIMEOUT: int = 120

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        if not cls.APP_ID:
            raise ValueError("MICROSOFT_APP_ID environment variable is required")
        if not cls.APP_PASSWORD:
            raise ValueError("MICROSOFT_APP_PASSWORD environment variable is required")
        if cls.APP_TYPE == "SingleTenant" and not cls.APP_TENANTID:
            raise ValueError("MICROSOFT_APP_TENANTID is required for SingleTenant apps")
        return True

    @classmethod
    def get_endpoint_url(cls, base_url: str) -> str:
        """
        Get full messaging endpoint URL

        Args:
            base_url: Base URL (e.g., "https://mybot.azurewebsites.net")

        Returns:
            Full messaging endpoint URL
        """
        return f"{base_url.rstrip('/')}{cls.MESSAGES_ENDPOINT}"


# Conversation state storage (simple in-memory for now)
# In production, use Azure Blob Storage or Redis
class ConversationStore:
    """Simple in-memory conversation history store"""

    def __init__(self):
        self._conversations = {}

    def get_history(self, conversation_id: str) -> list:
        """Get conversation history for a conversation ID"""
        return self._conversations.get(conversation_id, [])

    def add_message(self, conversation_id: str, role: str, message: str):
        """Add a message to conversation history"""
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []

        self._conversations[conversation_id].append({
            "role": role,
            "message": message
        })

        # Keep only last N messages
        max_messages = TeamsConfig.MAX_HISTORY_MESSAGES
        if len(self._conversations[conversation_id]) > max_messages:
            self._conversations[conversation_id] = self._conversations[conversation_id][-max_messages:]

    def clear_history(self, conversation_id: str):
        """Clear conversation history for a conversation ID"""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]


# Global conversation store instance
conversation_store = ConversationStore()
