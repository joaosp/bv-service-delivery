#!/bin/bash
# Activation helper script for BV Provisioning Agent environment

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Load environment variables from .env if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "📄 Loading environment from .env file..."
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Display activation message
echo "✅ BV Provisioning Agent environment activated (Claude Agent SDK)"
echo ""
echo "Available commands:"
echo "  python agent.py --interactive              # Start interactive mode"
echo "  python agent.py --opp-id <ID> --autonomous # Run autonomous extraction"
echo "  python agent.py --help                     # Show all options"
echo ""
echo "To deactivate: deactivate"
echo ""

# Check ANTHROPIC_API_KEY (optional - falls back to Claude CLI)
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ℹ️  ANTHROPIC_API_KEY not set - Using Claude CLI mode"
    echo "   The agent will use Claude Code CLI (requires npm install -g @anthropic-ai/claude-code)"
    echo "   To use API mode instead:"
    echo "   1. Copy .env.example to .env: cp .env.example .env"
    echo "   2. Edit .env with your API key"
    echo "   3. Re-run: source activate.sh"
    echo ""
else
    echo "✓ ANTHROPIC_API_KEY configured (API mode)"
    echo ""
fi

# Check Salesforce configuration
if [ ! -z "$SALESFORCE_ORG_USERNAME" ]; then
    echo "✓ Salesforce org: $SALESFORCE_ORG_USERNAME"
    echo ""
fi

# Check Microsoft Teams configuration (optional)
if [ ! -z "$AZURE_CLIENT_ID" ] && [ ! -z "$AZURE_CLIENT_SECRET" ] && [ ! -z "$AZURE_TENANT_ID" ]; then
    echo "✓ Microsoft Teams integration configured"
    echo "  Teams meeting transcripts will be extracted"
    echo ""
elif [ ! -z "$AZURE_CLIENT_ID" ]; then
    echo "⚠️  Microsoft Teams integration incomplete"
    echo "   Missing: AZURE_CLIENT_SECRET and/or AZURE_TENANT_ID"
    echo "   See TEAMS_SETUP.md for setup instructions"
    echo ""
else
    echo "ℹ️  Microsoft Teams integration not configured (optional)"
    echo "   Teams transcript extraction will be skipped"
    echo "   To enable: Add AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID to .env"
    echo ""
fi
