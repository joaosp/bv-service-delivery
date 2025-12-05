"""
Microsoft Teams Activity Handler

Processes incoming Teams messages and integrates with BVProvisioningAgent (Claude SDK)
"""

import asyncio
import time
from typing import Optional, Callable, List, Dict
from contextvars import ContextVar
from pathlib import Path
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ChannelAccount, Activity, ActivityTypes, Attachment

from agent import BVProvisioningAgent
from teams_config import TeamsConfig, conversation_store
from config import CLAUDE_MODEL, CANCELLATION_ENABLED
from cancellation import (
    get_conversation_cancellation_manager,
    set_current_conversation_id as set_cancellation_conversation_id
)

# Thread-local storage for conversation context
_conversation_context = ContextVar('conversation_id', default=None)


def set_current_conversation_id(conversation_id: str):
    """Set conversation ID for current thread/context"""
    _conversation_context.set(conversation_id)


def get_current_conversation_id() -> Optional[str]:
    """Get conversation ID for current thread/context"""
    return _conversation_context.get()


class TeamsActivityHandler(ActivityHandler):
    """
    Handles incoming Teams activities and routes them to Claude Agent SDK
    """

    def __init__(self):
        super().__init__()
        self.agent = BVProvisioningAgent()

    async def on_message_activity(self, turn_context: TurnContext):
        """
        Handle incoming message from Teams user.

        Supports cancellation:
        - /cancel command: Request cancellation with confirmation
        - Natural language: "cancel", "stop", "abort" etc. trigger confirmation
        - "yes"/"no" to confirm/abort pending cancellation

        Args:
            turn_context: Bot Framework turn context with message details
        """
        # Get message text
        user_message = turn_context.activity.text.strip()

        # Get conversation ID for maintaining context
        conversation_id = turn_context.activity.conversation.id

        # Get user info
        user_name = turn_context.activity.from_property.name if turn_context.activity.from_property else "User"

        print(f"\n[Teams] Message from {user_name}: {user_message}")

        # Get conversation-specific cancellation manager
        cancellation_mgr = get_conversation_cancellation_manager(conversation_id)
        set_cancellation_conversation_id(conversation_id)

        # Check for pending cancellation confirmation
        if CANCELLATION_ENABLED and cancellation_mgr.is_pending_confirmation():
            user_lower = user_message.lower().strip()
            if user_lower in ['yes', 'y', 'confirm']:
                result = cancellation_mgr.confirm_cancellation()
                await turn_context.send_activity(f"✅ {result.get('message', 'Operation cancelled.')}")
                return
            elif user_lower in ['no', 'n', 'abort', 'continue']:
                cancellation_mgr.abort_cancellation()
                await turn_context.send_activity("▶️ Cancellation aborted. Operation continues.")
                return
            # Otherwise, fall through and show reminder
            await turn_context.send_activity(
                "⚠️ Cancellation is pending. Type **yes** to confirm or **no** to continue."
            )
            return

        # Check for natural language cancellation intent (before command handling)
        if CANCELLATION_ENABLED and cancellation_mgr.detect_cancellation_intent(user_message):
            if cancellation_mgr.is_operation_running():
                result = cancellation_mgr.request_cancellation()
                await turn_context.send_activity(
                    f"⚠️ {result.get('message', '')}\n\n"
                    f"Type **yes** to confirm cancellation or **no** to continue."
                )
                return
            # If no operation running, let the message pass through

        # Handle commands
        if user_message.startswith('/'):
            await self._handle_command(turn_context, user_message, conversation_id)
            return

        # Send typing indicator
        if TeamsConfig.TYPING_INDICATOR_ENABLED:
            await self._send_typing_indicator(turn_context)

        # Send immediate acknowledgment message for user feedback
        if TeamsConfig.SHOW_PROCESSING_MESSAGE:
            await turn_context.send_activity("🤔 Processing your request...")
            if TeamsConfig.VERBOSE_LOGGING:
                print("[Teams] → Sent processing acknowledgment")

        # Set conversation context for tools to access
        set_current_conversation_id(conversation_id)

        try:
            # Get conversation history
            history = conversation_store.get_history(conversation_id)

            # Build context from history (limited to prevent buffer overflow)
            conversation_context = ""
            if history and TeamsConfig.CONVERSATION_HISTORY_ENABLED:
                conversation_context = "\n\nCONVERSATION HISTORY:\n"
                # Use configurable history limit (default 5 instead of 10)
                max_history = TeamsConfig.MAX_CONVERSATION_HISTORY_ITEMS
                for msg in history[-max_history:]:
                    role = msg["role"].capitalize()
                    conversation_context += f"{role}: {msg['message']}\n"
                conversation_context += "\n"

                # Truncate if conversation context is too large
                if len(conversation_context) > TeamsConfig.MAX_CONVERSATION_CONTEXT_SIZE:
                    conversation_context = conversation_context[-TeamsConfig.MAX_CONVERSATION_CONTEXT_SIZE:] + "\n[Earlier messages truncated]\n"

            # Use full system prompt (system prompts go to Claude, not to Teams)
            system_prompt = self.agent.system_prompt

            # Build full prompt for Claude agent
            full_prompt = f"""{system_prompt}

{conversation_context}USER: {user_message}
"""

            # Store user message in history
            conversation_store.add_message(conversation_id, "user", user_message)

            # Choose streaming or non-streaming based on configuration
            try:
                if TeamsConfig.STREAMING_ENABLED:
                    response_text = await self._process_streaming_response(turn_context, full_prompt)
                else:
                    response_text = await self.agent.query_prompt(full_prompt)
                    await self._send_message(turn_context, response_text)

            except Exception as e:
                # Check if buffer overflow error
                error_msg = str(e)
                if "exceeded maximum buffer size" in error_msg or "buffer" in error_msg.lower():
                    if TeamsConfig.VERBOSE_LOGGING:
                        print(f"[Teams] ⚠️  Buffer overflow detected, retrying with minimal context...")

                    # Retry with minimal prompt (no history, no system prompt)
                    minimal_prompt = f"USER: {user_message}"
                    await turn_context.send_activity("⚠️ Response too large, retrying with reduced context...")

                    if TeamsConfig.STREAMING_ENABLED:
                        response_text = await self._process_streaming_response(turn_context, minimal_prompt)
                    else:
                        response_text = await self.agent.query_prompt(minimal_prompt)
                        await self._send_message(turn_context, response_text)
                else:
                    # Re-raise if not a buffer overflow error
                    raise

            # Store assistant response in conversation history
            conversation_store.add_message(conversation_id, "assistant", response_text)

            # Send any queued files
            if TeamsConfig.AUTO_SEND_FILES:
                await self._send_queued_files(turn_context, conversation_id)

        except asyncio.TimeoutError:
            await turn_context.send_activity("⏱️ Request timed out. Please try again with a simpler query.")
        except Exception as e:
            print(f"[Teams] Error processing message: {str(e)}")
            import traceback
            traceback.print_exc()
            await turn_context.send_activity(f"❌ Sorry, I encountered an error: {str(e)}")
        finally:
            # Clear conversation context
            set_current_conversation_id(None)

    async def _process_streaming_response(self, turn_context: TurnContext, prompt: str) -> str:
        """
        Process agent response with streaming updates to Teams

        Args:
            turn_context: Bot turn context
            prompt: Full prompt to send to agent

        Returns:
            Final complete response text
        """
        text_buffer = ""
        final_response = ""
        last_activity_time = time.time()  # Track time of last activity sent

        if TeamsConfig.VERBOSE_LOGGING:
            print("[Teams] Starting streaming response...")

        # Start typing heartbeat background task if enabled
        heartbeat_task = None
        if TeamsConfig.TYPING_HEARTBEAT_ENABLED:
            heartbeat_task = asyncio.create_task(
                self._typing_heartbeat(turn_context, lambda: last_activity_time)
            )

        try:
            async for event in self.agent.query_prompt_streaming(prompt):
                event_type = event.get("type")

                if event_type == "tool_use":
                    # Flush any buffered text before showing tool use
                    # This text contains the agent's reasoning about why it's using the tool
                    if text_buffer:
                        if TeamsConfig.VERBOSE_LOGGING:
                            print(f"[Teams] → Sending buffered text (agent reasoning): {len(text_buffer)} chars")
                        await self._send_message(turn_context, text_buffer)
                        text_buffer = ""
                        # Update last activity time after sending reasoning
                        last_activity_time = time.time()

                    # Send typing indicator before tool notification if enabled
                    if TeamsConfig.TYPING_BEFORE_TOOL_USE and TeamsConfig.SHOW_TOOL_NOTIFICATIONS:
                        await self._send_typing_indicator(turn_context)
                        if TeamsConfig.VERBOSE_LOGGING:
                            print("[Teams] → Typing indicator (before tool use)")

                    # Optionally send generic tool use notification
                    # (if disabled, rely on agent's reasoning text sent above)
                    if TeamsConfig.SHOW_TOOL_NOTIFICATIONS:
                        tool_name = event.get("tool_name", "unknown")
                        if TeamsConfig.VERBOSE_LOGGING:
                            print(f"[Teams] → Sending tool notification: {tool_name}")
                        await turn_context.send_activity(f"🔧 Using tool: {tool_name}...")
                        # Update last activity time
                        last_activity_time = time.time()
                    else:
                        # Just log for debugging if verbose
                        if TeamsConfig.VERBOSE_LOGGING:
                            tool_name = event.get("tool_name", "unknown")
                            print(f"[Teams] Tool use: {tool_name} (notification suppressed, agent reasoning sent instead)")

                elif event_type == "text":
                    # Add to text buffer
                    text_content = event.get("content", "")
                    text_buffer += text_content
                    if TeamsConfig.VERBOSE_LOGGING:
                        print(f"[Teams] Buffering text: {len(text_buffer)} chars total")

                    # Send if buffer exceeds threshold
                    if len(text_buffer) >= TeamsConfig.STREAMING_TEXT_BUFFER_SIZE:
                        if TeamsConfig.VERBOSE_LOGGING:
                            print(f"[Teams] → Sending text chunk: {len(text_buffer)} chars")
                        await self._send_message(turn_context, text_buffer)
                        text_buffer = ""
                        # Update last activity time
                        last_activity_time = time.time()

                elif event_type == "done":
                    # Flush any remaining text buffer
                    if text_buffer:
                        if TeamsConfig.VERBOSE_LOGGING:
                            print(f"[Teams] → Sending final text: {len(text_buffer)} chars")
                        await self._send_message(turn_context, text_buffer)
                        text_buffer = ""
                        # Update last activity time
                        last_activity_time = time.time()

                    # Get final response for conversation history
                    final_response = event.get("full_response", "")
                    if TeamsConfig.VERBOSE_LOGGING:
                        print("[Teams] ✓ Response complete")

                elif event_type == "error":
                    # Handle error
                    error_msg = event.get("error", "Unknown error")
                    if TeamsConfig.VERBOSE_LOGGING:
                        print(f"[Teams] ✗ Error: {error_msg}")
                    await turn_context.send_activity(f"❌ Error: {error_msg}")
                    raise Exception(error_msg)

            return final_response

        except Exception as e:
            # Flush any pending text before raising
            if text_buffer:
                if TeamsConfig.VERBOSE_LOGGING:
                    print(f"[Teams] → Flushing buffer on error: {len(text_buffer)} chars")
                await self._send_message(turn_context, text_buffer)
            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] ✗ Exception during streaming: {str(e)}")
            raise

        finally:
            # Always cancel typing heartbeat task when done
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

    async def _send_file_as_text(self, turn_context: TurnContext, file_path: Path, description: str) -> bool:
        """
        Send file content as inline text in a code block

        Args:
            turn_context: Bot turn context
            file_path: Path to file
            description: User-friendly description

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check size limit
            if len(content) > TeamsConfig.INLINE_TEXT_FILE_THRESHOLD:
                return False  # Too large for inline

            # Determine language for syntax highlighting
            ext = file_path.suffix.lower()
            lang_map = {
                '.csv': 'csv',
                '.md': 'markdown',
                '.json': 'json',
                '.yaml': 'yaml',
                '.yml': 'yaml',
                '.txt': 'text',
                '.log': 'text'
            }
            lang = lang_map.get(ext, 'text')

            # Format message with code block
            message = f"📄 **{description}**\n\n```{lang}\n{content}\n```"

            # Check total message length
            if len(message) > TeamsConfig.MAX_MESSAGE_LENGTH:
                # Try without syntax highlighting
                message = f"📄 **{description}**\n\n```\n{content}\n```"

                if len(message) > TeamsConfig.MAX_MESSAGE_LENGTH:
                    return False  # Still too large

            await turn_context.send_activity(message)

            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] → Sent file as inline text: {file_path.name} ({len(content)} chars)")

            return True

        except UnicodeDecodeError:
            # Not a text file
            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] ✗ Cannot send {file_path.name} as text (binary file)")
            return False
        except Exception as e:
            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] ✗ Error sending file as text: {str(e)}")
            return False

    async def _send_file_with_consent(self, turn_context: TurnContext, file_path: Path, description: str) -> bool:
        """
        Send file using FileConsentCard (proper Teams file upload)

        Args:
            turn_context: Bot turn context
            file_path: Path to file
            description: User-friendly description

        Returns:
            True if successful, False otherwise
        """
        try:
            from botbuilder.schema import CardAction, ActionTypes
            from botbuilder.schema.teams import FileConsentCard, FileConsentCardResponse

            # Get file info
            file_size = file_path.stat().st_size
            file_name = file_path.name

            # Create file consent card
            file_card = FileConsentCard(
                description=description,
                size_in_bytes=file_size,
                accept_context={
                    "file_path": str(file_path),
                    "description": description
                },
                decline_context={
                    "file_name": file_name
                }
            )

            # Create attachment with file consent card
            attachment = Attachment(
                content_type="application/vnd.microsoft.teams.card.file.consent",
                name=file_name,
                content=file_card
            )

            # Create message with attachment
            reply = MessageFactory.text(f"📄 **{description}**")
            reply.attachments = [attachment]

            await turn_context.send_activity(reply)

            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] → Sent file consent card: {file_name} ({file_size} bytes)")

            return True

        except Exception as e:
            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Teams] ✗ Error sending file consent card: {str(e)}")
            return False

    async def _send_queued_files(self, turn_context: TurnContext, conversation_id: str):
        """
        Retrieve and send all queued files for this conversation
        Uses smart routing: text files as inline, large files via FileConsentCard

        Args:
            turn_context: Bot turn context
            conversation_id: Teams conversation ID
        """
        from file_queue import file_queue

        # Get files from queue
        files = file_queue.get_files(conversation_id)

        if not files:
            return

        if TeamsConfig.VERBOSE_LOGGING:
            print(f"[Teams] Found {len(files)} file(s) in queue")

        # Sort by priority (high -> normal -> low)
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        files.sort(key=lambda f: priority_order.get(f.get('priority', 'normal'), 1))

        sent_count = 0
        skipped = []

        for file_info in files:
            file_path = Path(file_info['file_path'])
            description = file_info.get('description', file_path.name)

            # Check if file exists
            if not file_path.exists():
                skipped.append(f"{file_path.name} (not found)")
                continue

            # Check file size
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > TeamsConfig.MAX_FILE_SIZE_MB:
                skipped.append(f"{file_path.name} ({size_mb:.1f}MB > {TeamsConfig.MAX_FILE_SIZE_MB}MB limit)")
                continue

            try:
                # Determine delivery method based on file type and size
                file_ext = file_path.suffix.lower()
                is_text_file = file_ext in TeamsConfig.SUPPORTED_TEXT_EXTENSIONS
                delivery_method = TeamsConfig.FILE_DELIVERY_METHOD

                success = False

                # Try inline text first for supported text files
                if delivery_method in ["auto", "inline"] and is_text_file:
                    if TeamsConfig.VERBOSE_LOGGING:
                        print(f"[Teams] Attempting inline text delivery for {file_path.name}")
                    success = await self._send_file_as_text(turn_context, file_path, description)

                # Fall back to FileConsentCard if inline failed or not applicable
                if not success and delivery_method in ["auto", "consent"]:
                    if TeamsConfig.VERBOSE_LOGGING:
                        print(f"[Teams] Attempting FileConsentCard delivery for {file_path.name}")
                    success = await self._send_file_with_consent(turn_context, file_path, description)

                if success:
                    sent_count += 1
                else:
                    skipped.append(f"{file_path.name} (delivery failed)")

            except Exception as e:
                skipped.append(f"{file_path.name} (error: {str(e)})")
                if TeamsConfig.VERBOSE_LOGGING:
                    print(f"[Teams] ✗ Failed to send {file_path.name}: {str(e)}")

        # Send warning for skipped files
        if skipped:
            warning_msg = "⚠️ **Some files could not be sent:**\n" + "\n".join(f"• {s}" for s in skipped)
            await turn_context.send_activity(warning_msg)

        # Summary
        if TeamsConfig.VERBOSE_LOGGING:
            print(f"[Teams] ✓ Sent {sent_count}/{len(files)} file(s)")

    async def _typing_heartbeat(self, turn_context: TurnContext, get_last_activity_time: Callable[[], float]):
        """
        Send periodic typing indicators during long operations

        Args:
            turn_context: Bot turn context
            get_last_activity_time: Callable that returns timestamp of last activity sent
        """
        try:
            while True:
                await asyncio.sleep(1)  # Check every second

                # Send typing indicator if no activity in X seconds
                time_since_last = time.time() - get_last_activity_time()
                if time_since_last > TeamsConfig.TYPING_HEARTBEAT_INTERVAL:
                    await self._send_typing_indicator(turn_context)
                    if TeamsConfig.VERBOSE_LOGGING:
                        print("[Teams] → Typing indicator (heartbeat)")

        except asyncio.CancelledError:
            # Task cancelled when streaming completes
            if TeamsConfig.VERBOSE_LOGGING:
                print("[Teams] Typing heartbeat task stopped")

    async def _handle_command(self, turn_context: TurnContext, command: str, conversation_id: str):
        """Handle slash commands"""
        if command == '/help':
            help_text = """**BV Provisioning Agent - Commands**

Available commands:
- `/help` - Show this help message
- `/clear` - Clear conversation history
- `/status` - Show bot status and model info
- `/cancel` - Cancel current operation (requires confirmation)

**Example requests:**
- Extract provisioning data for opportunity [ID]
- What opportunities are open for [Company Name]?
- Show me the status of provisioning for opportunity [ID]
- What are the critical mandatory fields?
"""
            await turn_context.send_activity(help_text)

        elif command == '/clear':
            conversation_store.clear_history(conversation_id)
            await turn_context.send_activity("✨ Conversation history cleared.")

        elif command == '/cancel':
            if not CANCELLATION_ENABLED:
                await turn_context.send_activity("⚠️ Cancellation is disabled.")
                return

            cancellation_mgr = get_conversation_cancellation_manager(conversation_id)

            if cancellation_mgr.is_pending_confirmation():
                # Double /cancel = confirm
                result = cancellation_mgr.confirm_cancellation()
                await turn_context.send_activity(f"✅ {result.get('message', 'Operation cancelled.')}")
            elif cancellation_mgr.is_operation_running():
                result = cancellation_mgr.request_cancellation()
                await turn_context.send_activity(
                    f"⚠️ {result.get('message', '')}\n\n"
                    f"Type `/cancel` again or **yes** to confirm, or **no** to continue."
                )
            else:
                await turn_context.send_activity("ℹ️ No operation is currently running.")

        elif command == '/status':
            status_text = f"""**Bot Status**
- Model: {CLAUDE_MODEL}
- Status: ✅ Online
- Conversation history: {"Enabled" if TeamsConfig.CONVERSATION_HISTORY_ENABLED else "Disabled"}
- Cancellation: {"Enabled" if CANCELLATION_ENABLED else "Disabled"}
"""
            # Add current operation status if running
            if CANCELLATION_ENABLED:
                cancellation_mgr = get_conversation_cancellation_manager(conversation_id)
                if cancellation_mgr.is_operation_running():
                    state = cancellation_mgr.get_current_state()
                    opp_id = cancellation_mgr.get_opportunity_id()
                    status_text += f"- Current operation: {state.value}"
                    if opp_id:
                        status_text += f" (Opportunity: {opp_id})"
                    status_text += "\n"

            await turn_context.send_activity(status_text)

        else:
            await turn_context.send_activity(f"Unknown command: {command}. Type `/help` for available commands.")

    async def _send_typing_indicator(self, turn_context: TurnContext):
        """Send typing indicator to show bot is processing"""
        typing_activity = Activity(
            type=ActivityTypes.typing,
            relates_to=turn_context.activity.relates_to
        )
        await turn_context.send_activity(typing_activity)

    async def _send_message(self, turn_context: TurnContext, message: str):
        """
        Send message to Teams, handling length limits

        Args:
            turn_context: Bot turn context
            message: Message to send
        """
        # Check message length
        if len(message) > TeamsConfig.MAX_MESSAGE_LENGTH:
            # Split into chunks
            chunks = [message[i:i+TeamsConfig.MAX_MESSAGE_LENGTH]
                     for i in range(0, len(message), TeamsConfig.MAX_MESSAGE_LENGTH)]

            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = f"(continued...)\n\n{chunk}"
                await turn_context.send_activity(chunk)
        else:
            await turn_context.send_activity(message)

    async def on_members_added_activity(self, members_added: list[ChannelAccount], turn_context: TurnContext):
        """
        Handle when bot is added to a conversation or user joins

        Args:
            members_added: List of new members
            turn_context: Bot turn context
        """
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                welcome_message = """👋 **Welcome to BV Provisioning Agent!**

I can help you with:
- Extract provisioning data from Salesforce opportunities
- Query Salesforce for accounts, opportunities, contacts, documents
- Check status of existing provisioning files
- Answer questions about BroadVoice requirements and validation rules

Type `/help` to see available commands or just ask me a question!
"""
                await turn_context.send_activity(welcome_message)
