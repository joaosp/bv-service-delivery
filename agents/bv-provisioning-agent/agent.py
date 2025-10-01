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
    PROVS_DIR
)
from tools import ALL_TOOLS, TOOL_SCHEMAS


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


    async def run(self, opportunity_id: str) -> dict:
        """
        Execute the provisioning extraction workflow using Claude Agent SDK

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
        print("\n" + "=" * 70 + "\n")

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

            # Configure SDK options with MCP server
            # List all our custom tools explicitly
            custom_tools = [
                "mcp__bv__extract_salesforce_data",
                "mcp__bv__clean_transcript",
                "mcp__bv__analyze_documents",
                "mcp__bv__validate_attributes",
                "mcp__bv__generate_provisioning_csv",
                "mcp__bv__generate_status_report",
                "mcp__bv__query_salesforce_general",
                "mcp__bv__check_extraction_status",
                "mcp__bv__read_provisioning_file"
            ]

            options = ClaudeAgentOptions(
                model=CLAUDE_MODEL,
                cwd=str(PROJECT_ROOT),  # Set working directory
                add_dirs=[str(DATA_DIR), str(PROVS_DIR)],  # Allow access to data directories
                mcp_servers={"bv": self.mcp_server},
                allowed_tools=custom_tools,  # Only our custom tools (explicit list)
                permission_mode="acceptEdits"  # Auto-approve our custom tools
            )

            # Use ClaudeSDKClient for better control
            async with ClaudeSDKClient(options=options) as client:
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
            print("✅ AGENT COMPLETED")
            print("=" * 70)

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

    async def run_interactive(self, initial_context: Optional[str] = None) -> None:
        """
        Run agent in interactive mode with continuous conversation

        Args:
            initial_context: Optional initial context (e.g., opportunity ID)
        """
        print("=" * 70)
        print(WELCOME_MESSAGE)
        print("=" * 70)

        # Add initial context if provided
        if initial_context:
            print(f"\n📋 Context: {initial_context}\n")

        # Interactive conversation loop
        while True:
            try:
                # Get user input
                user_input = input(INTERACTIVE_PROMPT).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith('/'):
                    if user_input == '/exit':
                        print("\n👋 Goodbye!")
                        break
                    elif user_input == '/help':
                        print(INTERACTIVE_HELP)
                        continue
                    elif user_input == '/clear':
                        self.conversation_history = []
                        print("\n✨ Conversation history cleared.\n")
                        continue
                    else:
                        print(f"Unknown command: {user_input}. Type /help for available commands.")
                        continue

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

                # Configure SDK options with MCP server
                # List all our custom tools explicitly
                custom_tools = [
                    "mcp__bv__extract_salesforce_data",
                    "mcp__bv__clean_transcript",
                    "mcp__bv__analyze_documents",
                    "mcp__bv__validate_attributes",
                    "mcp__bv__generate_provisioning_csv",
                    "mcp__bv__generate_status_report",
                    "mcp__bv__query_salesforce_general",
                    "mcp__bv__check_extraction_status",
                    "mcp__bv__read_provisioning_file"
                ]

                options = ClaudeAgentOptions(
                    model=CLAUDE_MODEL,
                    cwd=str(PROJECT_ROOT),  # Set working directory
                    add_dirs=[str(DATA_DIR), str(PROVS_DIR)],  # Allow access to data directories
                    mcp_servers={"bv": self.mcp_server},
                    allowed_tools=custom_tools,  # Only our custom tools (explicit list)
                    permission_mode="acceptEdits"  # Auto-approve our custom tools
                )

                try:
                    # Use ClaudeSDKClient for better control
                    async with ClaudeSDKClient(options=options) as client:
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
                print("\n\n⚠️  Use /exit to quit gracefully")
                continue
            except EOFError:
                print("\n\n👋 Goodbye!")
                break


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
