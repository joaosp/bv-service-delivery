#!/usr/bin/env python3
"""
BV Provisioning Agent

An AI agent built with Claude Agent SDK that helps with BroadVoice provisioning workflows.

Usage:
    # Interactive mode (default)
    python agent.py --interactive

    # Autonomous extraction mode
    python agent.py --opp-id <OPPORTUNITY_ID> --autonomous
"""

import argparse
import asyncio
import signal
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import json

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

try:
    from claude_agent_sdk import (
        query,
        ClaudeSDKClient,
        ClaudeAgentOptions,
        create_sdk_mcp_server,
        CLINotFoundError,
        ProcessError
    )
    SDK_AVAILABLE = True
except ImportError:
    print("⚠️  Warning: claude-agent-sdk not installed. Please run: pip install claude-agent-sdk")
    SDK_AVAILABLE = False
    sys.exit(1)

from config import (
    CLAUDE_MODEL,
    SYSTEM_PROMPT_FILE,
    EXTRACTION_PROMPT_FILE,
    VALIDATION_PROMPT_FILE,
    WELCOME_MESSAGE,
    INTERACTIVE_PROMPT,
    AGENT_PREFIX,
    INTERACTIVE_HELP,
    PROJECT_ROOT,
    DATA_DIR,
    PROVS_DIR,
    BHIVE_MCP_ENABLED,
    BHIVE_MCP_SERVER_URL,
    CANCELLATION_ENABLED
)
from tools import ALL_TOOLS, TOOL_SCHEMAS
from cancellation import (
    get_cancellation_manager,
    cancellation_manager as global_cancellation_manager,
    OperationState
)


# Custom tools list for Claude SDK
CUSTOM_TOOLS = [
    # Salesforce extraction tools
    "mcp__bv__extract_salesforce_data",
    "mcp__bv__clean_transcript",
    "mcp__bv__analyze_documents",
    "mcp__bv__validate_attributes",
    "mcp__bv__generate_provisioning_csv",
    "mcp__bv__generate_status_report",
    "mcp__bv__query_salesforce_general",
    "mcp__bv__check_extraction_status",
    "mcp__bv__read_provisioning_file",
    "mcp__bv__queue_file_for_teams",
    # B-hive provisioning tools
    "mcp__bv__save_bhive_provisioning_data",
    "mcp__bv__provision_to_bhive",
    "mcp__bv__check_bhive_provisioning_status",
    "mcp__bv__generate_bhive_report",
    # Cancellation tool
    "mcp__bv__cancel_operation"
]


class BVProvisioningAgent:
    """BroadVoice Provisioning Extraction Agent using Claude Agent SDK"""

    def __init__(self):
        """Initialize the agent"""
        self.system_prompt = self._load_system_prompt()
        self.tools = ALL_TOOLS
        self.tool_schemas = TOOL_SCHEMAS
        self.conversation_history = []

        # Create MCP server with our custom tools
        self.mcp_server = create_sdk_mcp_server(
            name="bv_provisioning",
            version="1.0.0",
            tools=ALL_TOOLS
        )

        # Check b-hive MCP server connectivity if enabled
        self.bhive_available = False
        if BHIVE_MCP_ENABLED:
            self._check_bhive_connectivity()

    def _check_bhive_connectivity(self):
        """Check if b-hive MCP server is reachable at startup"""
        from bhive_client import BHiveMCPClient
        client = BHiveMCPClient()
        result = client.check_health_sync()

        if result.get("success"):
            print(f"✅ B-hive MCP server connected ({BHIVE_MCP_SERVER_URL})")
            self.bhive_available = True
        else:
            print(f"⚠️  B-hive MCP server unavailable: {result.get('error')}")
            print(f"   URL: {BHIVE_MCP_SERVER_URL}")
            print(f"   B-hive provisioning features will be disabled.")
            self.bhive_available = False

    def _load_system_prompt(self) -> str:
        """Load and combine all system prompts"""
        prompts = []

        # Load main system prompt
        if SYSTEM_PROMPT_FILE.exists():
            with open(SYSTEM_PROMPT_FILE, 'r') as f:
                prompts.append(f.read())

        # Load extraction methodology
        if EXTRACTION_PROMPT_FILE.exists():
            with open(EXTRACTION_PROMPT_FILE, 'r') as f:
                prompts.append("\n\n---\n\n")
                prompts.append(f.read())

        # Load validation requirements
        if VALIDATION_PROMPT_FILE.exists():
            with open(VALIDATION_PROMPT_FILE, 'r') as f:
                prompts.append("\n\n---\n\n")
                prompts.append(f.read())

        return ''.join(prompts)

    def _create_sdk_options(self) -> 'ClaudeAgentOptions':
        """
        Create ClaudeAgentOptions for SDK client

        Returns:
            Configured ClaudeAgentOptions instance
        """
        return ClaudeAgentOptions(
            model=CLAUDE_MODEL,
            cwd=str(PROJECT_ROOT),
            add_dirs=[str(DATA_DIR)],
            mcp_servers={"bv": self.mcp_server},
            allowed_tools=CUSTOM_TOOLS,
            permission_mode="acceptEdits"
        )

    async def query_prompt(self, prompt: str) -> str:
        """
        Query Claude Agent SDK with a prompt and return response text

        Args:
            prompt: Full prompt to send to agent

        Returns:
            Agent response text (combined tool outputs and text)
        """
        response_text = ""
        tool_outputs = []

        async with ClaudeSDKClient(options=self._create_sdk_options()) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                class_name = message.__class__.__name__

                # Skip system/result messages
                if class_name in ['SystemMessage', 'ResultMessage']:
                    continue

                # Handle AssistantMessage
                if class_name == 'AssistantMessage':
                    content = getattr(message, 'content', [])
                    for block in content:
                        block_type = block.__class__.__name__

                        if block_type == 'TextBlock':
                            text = getattr(block, 'text', '')
                            if text:
                                response_text += text

                        elif block_type == 'ToolUseBlock':
                            tool_name = getattr(block, 'name', 'unknown')
                            if 'mcp__bv__' in tool_name:
                                tool_name = tool_name.replace('mcp__bv__', '')
                            tool_outputs.append(f"🔧 Using tool: {tool_name}")

                elif class_name == 'UserMessage':
                    continue

        # Combine tool outputs with response
        if tool_outputs:
            full_response = "\n".join(tool_outputs) + "\n\n" + response_text
        else:
            full_response = response_text

        return full_response.strip() or "I processed your request but have no additional information to share."

    async def query_prompt_streaming(self, prompt: str):
        """
        Query Claude Agent SDK with a prompt and yield incremental updates

        Args:
            prompt: Full prompt to send to agent

        Yields:
            Dictionary events:
            - {"type": "tool_use", "tool_name": str} - when tool is used
            - {"type": "text", "content": str} - text block from agent
            - {"type": "done", "full_response": str} - final complete response
        """
        from teams_config import TeamsConfig

        response_text = ""
        tool_outputs = []

        try:
            if TeamsConfig.VERBOSE_LOGGING:
                print("[Agent SDK] Starting query...")

            async with ClaudeSDKClient(options=self._create_sdk_options()) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    class_name = message.__class__.__name__

                    # Skip system/result messages
                    if class_name in ['SystemMessage', 'ResultMessage']:
                        continue

                    # Handle AssistantMessage
                    if class_name == 'AssistantMessage':
                        content = getattr(message, 'content', [])
                        for block in content:
                            block_type = block.__class__.__name__

                            if block_type == 'TextBlock':
                                text = getattr(block, 'text', '')
                                if text:
                                    response_text += text
                                    if TeamsConfig.VERBOSE_LOGGING:
                                        print(f"[Agent SDK] Text block: {len(text)} chars")
                                    # Yield text event
                                    yield {
                                        "type": "text",
                                        "content": text
                                    }

                            elif block_type == 'ToolUseBlock':
                                tool_name = getattr(block, 'name', 'unknown')
                                if 'mcp__bv__' in tool_name:
                                    tool_name = tool_name.replace('mcp__bv__', '')
                                tool_outputs.append(f"🔧 Using tool: {tool_name}")
                                if TeamsConfig.VERBOSE_LOGGING:
                                    print(f"[Agent SDK] Tool use: {tool_name}")
                                # Yield tool use event
                                yield {
                                    "type": "tool_use",
                                    "tool_name": tool_name
                                }

                    elif class_name == 'UserMessage':
                        continue

            # Build final response
            if tool_outputs:
                full_response = "\n".join(tool_outputs) + "\n\n" + response_text
            else:
                full_response = response_text

            final_response = full_response.strip() or "I processed your request but have no additional information to share."

            if TeamsConfig.VERBOSE_LOGGING:
                print("[Agent SDK] Streaming complete")

            # Yield completion event
            yield {
                "type": "done",
                "full_response": final_response
            }

        except Exception as e:
            if TeamsConfig.VERBOSE_LOGGING:
                print(f"[Agent SDK] Error: {str(e)}")
            # Yield error event
            yield {
                "type": "error",
                "error": str(e)
            }

    async def run(self, opportunity_id: str) -> dict:
        """
        Execute the provisioning extraction workflow using Claude Agent SDK

        Supports cancellation via Ctrl+C (immediate, no confirmation in autonomous mode).

        Args:
            opportunity_id: Salesforce opportunity ID or name

        Returns:
            Dictionary with extraction results
        """
        print("=" * 70)
        print("🤖 BV PROVISIONING AGENT (Claude Agent SDK)")
        print("=" * 70)
        print(f"\nOpportunity: {opportunity_id}")
        print(f"Model: {CLAUDE_MODEL}")
        if CANCELLATION_ENABLED:
            print("Press Ctrl+C to cancel at any time")
        print("\n" + "=" * 70 + "\n")

        # Get cancellation manager
        cancellation_mgr = get_cancellation_manager()
        cancellation_mgr.set_opportunity_id(opportunity_id)

        # Set up SIGINT handler for autonomous mode (immediate cancellation)
        original_sigint_handler = signal.getsignal(signal.SIGINT)
        cancelled = False

        def autonomous_cancel_handler(signum, frame):
            """Handle Ctrl+C in autonomous mode - immediate cancellation"""
            nonlocal cancelled
            if CANCELLATION_ENABLED:
                print("\n\n[Ctrl+C] Cancellation requested...")
                cancellation_mgr.request_cancellation()
                cancellation_mgr.confirm_cancellation()
                cancelled = True
                print("Cancellation signal sent. Waiting for operation to stop...\n")

        if CANCELLATION_ENABLED:
            signal.signal(signal.SIGINT, autonomous_cancel_handler)

        # Build the prompt with system instructions and user request
        full_prompt = f"""{self.system_prompt}

USER REQUEST:
Please extract BroadVoice provisioning requirements for opportunity: {opportunity_id}

Follow the complete workflow:
1. Extract all Salesforce data using extract_salesforce_data tool
2. Analyze all documents and transcripts systematically
3. Apply 4-pass extraction methodology
4. Generate provisioning CSV with all 80 attributes
5. Create comprehensive status report

Begin the extraction process now.
"""

        try:
            print("🔄 Connecting to Claude Agent SDK...\n")

            # Use ClaudeSDKClient for better control
            async with ClaudeSDKClient(options=self._create_sdk_options()) as client:
                # Send the prompt
                await client.query(full_prompt)

                # Process responses
                async for message in client.receive_response():
                    # Check if cancelled
                    if cancelled:
                        print("\n⚠️ Operation cancelled by user")
                        break

                    # Get message class name
                    class_name = message.__class__.__name__

                    # Skip system/result messages
                    if class_name in ['SystemMessage', 'ResultMessage']:
                        continue

                    # Handle AssistantMessage - contains text and tool use blocks
                    if class_name == 'AssistantMessage':
                        content = getattr(message, 'content', [])
                        for block in content:
                            block_type = block.__class__.__name__

                            if block_type == 'TextBlock':
                                # Extract text from TextBlock
                                text = getattr(block, 'text', '')
                                if text:
                                    print(f"\n{AGENT_PREFIX}{text}")

                            elif block_type == 'ToolUseBlock':
                                # Show tool usage
                                tool_name = getattr(block, 'name', 'unknown')
                                if 'mcp__bv__' in tool_name:
                                    tool_name = tool_name.replace('mcp__bv__', '')
                                print(f"\n🔧 Using tool: {tool_name}...")

                    # Skip UserMessage (tool results are handled internally)
                    elif class_name == 'UserMessage':
                        continue

            print("\n" + "=" * 70)
            if cancelled:
                print("⚠️ AGENT CANCELLED")
                print("Downloaded data has been preserved.")
            else:
                print("✅ AGENT COMPLETED")
            print("=" * 70)

            if cancelled:
                return {
                    "success": False,
                    "cancelled": True,
                    "opportunity_id": opportunity_id,
                    "message": "Extraction cancelled by user. Downloaded data preserved."
                }

            return {
                "success": True,
                "opportunity_id": opportunity_id,
                "message": "Extraction completed successfully"
            }

        except CLINotFoundError:
            print("\n❌ Error: Claude Code CLI not found")
            print("Please install Claude Code:")
            print("  npm install -g @anthropic-ai/claude-code")
            return {
                "success": False,
                "error": "CLI not found"
            }
        except ProcessError as e:
            print(f"\n❌ Process error: {e.exit_code}")
            return {
                "success": False,
                "error": f"Process error: {e.exit_code}"
            }
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # Restore original SIGINT handler
            if CANCELLATION_ENABLED:
                signal.signal(signal.SIGINT, original_sigint_handler)
            # Reset cancellation state
            cancellation_mgr.reset()

    async def run_interactive(self, initial_context: Optional[str] = None) -> None:
        """
        Run agent in interactive mode with continuous conversation

        Supports cancellation:
        - /cancel command: Request cancellation with confirmation
        - Ctrl+C: Emergency stop - cancels immediately without confirmation
        - Natural language: "cancel", "stop", "abort" etc. trigger confirmation

        Args:
            initial_context: Optional initial context (e.g., opportunity ID)
        """
        print("=" * 70)
        print(WELCOME_MESSAGE)
        print("=" * 70)

        # Add initial context if provided
        if initial_context:
            print(f"\n📋 Context: {initial_context}\n")

        # Get cancellation manager for this session
        cancellation_mgr = get_cancellation_manager()

        # Set up SIGINT handler for emergency cancellation (Ctrl+C bypasses confirmation)
        original_sigint_handler = signal.getsignal(signal.SIGINT)

        def emergency_cancel_handler(signum, frame):
            """Handle Ctrl+C - immediate cancellation without confirmation"""
            if CANCELLATION_ENABLED and cancellation_mgr.is_operation_running():
                print("\n\n[Ctrl+C] Emergency cancellation triggered...")
                cancellation_mgr.request_cancellation()
                result = cancellation_mgr.confirm_cancellation()
                print(f"\n{AGENT_PREFIX}{result.get('message', 'Operation cancelled.')}\n")
            else:
                # No operation running, restore original behavior
                print("\n\n[Ctrl+C] Use /exit to quit gracefully")

        if CANCELLATION_ENABLED:
            signal.signal(signal.SIGINT, emergency_cancel_handler)

        try:
            # Interactive conversation loop
            while True:
                try:
                    # Get user input
                    user_input = input(INTERACTIVE_PROMPT).strip()

                    if not user_input:
                        continue

                    # Check for pending cancellation confirmation
                    if CANCELLATION_ENABLED and cancellation_mgr.is_pending_confirmation():
                        if user_input.lower() in ['yes', 'y', 'confirm']:
                            result = cancellation_mgr.confirm_cancellation()
                            print(f"\n{AGENT_PREFIX}{result.get('message', 'Operation cancelled.')}\n")
                            continue
                        elif user_input.lower() in ['no', 'n', 'cancel']:
                            cancellation_mgr.abort_cancellation()
                            print(f"\n{AGENT_PREFIX}Cancellation aborted. Operation continues.\n")
                            continue

                    # Handle commands
                    if user_input.startswith('/'):
                        if user_input == '/exit':
                            print("\n👋 Goodbye!")
                            break
                        elif user_input == '/help':
                            print(INTERACTIVE_HELP)
                            print("\nCancellation Commands:")
                            print("  /cancel         Cancel current operation (requires confirmation)")
                            print("  Ctrl+C          Emergency cancel (no confirmation)")
                            continue
                        elif user_input == '/clear':
                            self.conversation_history = []
                            print("\n✨ Conversation history cleared.\n")
                            continue
                        elif user_input == '/cancel':
                            if not CANCELLATION_ENABLED:
                                print(f"\n{AGENT_PREFIX}Cancellation is disabled.\n")
                                continue
                            if cancellation_mgr.is_operation_running():
                                result = cancellation_mgr.request_cancellation()
                                print(f"\n{AGENT_PREFIX}{result.get('message', '')}")
                                print(f"{AGENT_PREFIX}Type 'yes' to confirm or 'no' to continue.\n")
                            else:
                                print(f"\n{AGENT_PREFIX}No operation is currently running.\n")
                            continue
                        else:
                            print(f"Unknown command: {user_input}. Type /help for available commands.")
                            continue

                    # Check for natural language cancellation intent
                    if CANCELLATION_ENABLED and cancellation_mgr.detect_cancellation_intent(user_input):
                        if cancellation_mgr.is_operation_running():
                            result = cancellation_mgr.request_cancellation()
                            print(f"\n{AGENT_PREFIX}{result.get('message', '')}")
                            print(f"{AGENT_PREFIX}Type 'yes' to confirm or 'no' to continue.\n")
                            continue
                        # If no operation running, let the message pass through to Claude

                    # Build prompt with system instructions and conversation history
                    conversation_context = "\n\n".join([
                        f"{'User' if i % 2 == 0 else 'Assistant'}: {msg}"
                        for i, msg in enumerate(self.conversation_history)
                    ])

                    # Build conversation history section
                    history_section = ""
                    if conversation_context:
                        history_section = f"CONVERSATION HISTORY:\n{conversation_context}\n\n"

                    full_prompt = f"""{self.system_prompt}

{history_section}USER: {user_input}
"""

                    # Add to conversation history
                    self.conversation_history.append(user_input)

                    # Query the agent
                    print()  # New line for response
                    response_text = ""

                    try:
                        # Use ClaudeSDKClient for better control
                        async with ClaudeSDKClient(options=self._create_sdk_options()) as client:
                            # Send the prompt
                            await client.query(full_prompt)

                            # Process responses
                            async for message in client.receive_response():
                                # Get message class name
                                class_name = message.__class__.__name__

                                # Skip system/result messages
                                if class_name in ['SystemMessage', 'ResultMessage']:
                                    continue

                                # Handle AssistantMessage - contains text and tool use blocks
                                if class_name == 'AssistantMessage':
                                    content = getattr(message, 'content', [])
                                    for block in content:
                                        block_type = block.__class__.__name__

                                        if block_type == 'TextBlock':
                                            # Extract text from TextBlock
                                            text = getattr(block, 'text', '')
                                            if text:
                                                print(f"\n{AGENT_PREFIX}{text}")
                                                response_text += text

                                        elif block_type == 'ToolUseBlock':
                                            # Show tool usage
                                            tool_name = getattr(block, 'name', 'unknown')
                                            if 'mcp__bv__' in tool_name:
                                                tool_name = tool_name.replace('mcp__bv__', '')
                                            print(f"\n🔧 Using tool: {tool_name}...")

                                # Skip UserMessage (tool results are handled internally)
                                elif class_name == 'UserMessage':
                                    continue

                        print()  # New line after response

                        # Add response to history
                        if response_text:
                            self.conversation_history.append(response_text)

                    except CLINotFoundError:
                        print(f"\n{AGENT_PREFIX}⚠️  Claude Code CLI not found. Please install: npm install -g @anthropic-ai/claude-code\n")
                    except ProcessError as e:
                        print(f"\n{AGENT_PREFIX}⚠️  Process error: {e.exit_code}\n")
                    except Exception as e:
                        print(f"\n{AGENT_PREFIX}⚠️  Error: {str(e)}\n")

                except KeyboardInterrupt:
                    # This should be handled by our signal handler, but just in case
                    print("\n\n[Ctrl+C] Use /exit to quit gracefully")
                    continue
                except EOFError:
                    print("\n\n👋 Goodbye!")
                    break
        finally:
            # Restore original SIGINT handler
            if CANCELLATION_ENABLED:
                signal.signal(signal.SIGINT, original_sigint_handler)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="BV Provisioning Agent - Interactive assistant for Salesforce provisioning workflows",
        epilog="Examples:\n"
               "  python agent.py --interactive\n"
               "  python agent.py --opp-id 0065e00000XxxxxxAAA --autonomous\n"
               "  python agent.py --interactive --context 'ABC Property Management'",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--interactive',
        action='store_true',
        default=False,
        help='Run in interactive conversational mode (default if no --opp-id)'
    )
    mode_group.add_argument(
        '--autonomous',
        action='store_true',
        default=False,
        help='Run in autonomous extraction mode (requires --opp-id)'
    )

    # Options
    parser.add_argument(
        '--opp-id',
        type=str,
        help='Salesforce opportunity ID for extraction or initial context'
    )
    parser.add_argument(
        '--context',
        type=str,
        help='Initial context for interactive mode (customer name, account, etc.)'
    )

    args = parser.parse_args()

    # Check if SDK is available
    if not SDK_AVAILABLE:
        print("❌ Claude Agent SDK is required but not installed.")
        print("Install it with: pip install claude-agent-sdk")
        sys.exit(1)

    # Determine mode
    if args.autonomous:
        if not args.opp_id:
            parser.error("--autonomous requires --opp-id")
        mode = 'autonomous'
    elif args.interactive:
        mode = 'interactive'
    elif args.opp_id:
        # If opp-id provided without mode flag, default to autonomous
        mode = 'autonomous'
    else:
        # Default to interactive
        mode = 'interactive'

    # Create agent
    agent = BVProvisioningAgent()

    try:
        if mode == 'interactive':
            # Interactive mode
            initial_context = args.context or args.opp_id
            asyncio.run(agent.run_interactive(initial_context))
            sys.exit(0)
        else:
            # Autonomous mode
            result = asyncio.run(agent.run(args.opp_id))

            if result["success"]:
                print(f"\n✅ Successfully processed opportunity: {args.opp_id}")
                sys.exit(0)
            else:
                print(f"\n❌ Failed to process opportunity: {args.opp_id}")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Agent interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
