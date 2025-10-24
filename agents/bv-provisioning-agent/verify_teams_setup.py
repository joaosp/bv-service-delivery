#!/usr/bin/env python3
"""
Verify Teams Bot Setup

Checks that all required environment variables and dependencies are configured
correctly before running the Teams bot.

Usage:
    python verify_teams_setup.py
"""

import os
import sys
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text):
    """Print section header"""
    print(f"\n{BLUE}{'=' * 70}")
    print(f"{text}")
    print(f"{'=' * 70}{RESET}\n")


def check_env_var(var_name, required=True):
    """Check if environment variable is set"""
    value = os.getenv(var_name)
    if value:
        # Mask sensitive values
        if 'PASSWORD' in var_name or 'SECRET' in var_name or 'KEY' in var_name:
            display_value = value[:8] + "..." if len(value) > 8 else "***"
        else:
            display_value = value
        print(f"  {GREEN}✓{RESET} {var_name}: {display_value}")
        return True
    else:
        if required:
            print(f"  {RED}✗{RESET} {var_name}: NOT SET (required)")
            return False
        else:
            print(f"  {YELLOW}○{RESET} {var_name}: NOT SET (optional)")
            return True


def check_dependency(module_name, package_name=None):
    """Check if Python package is installed"""
    if package_name is None:
        package_name = module_name

    try:
        __import__(module_name)
        print(f"  {GREEN}✓{RESET} {package_name}")
        return True
    except ImportError:
        print(f"  {RED}✗{RESET} {package_name}: NOT INSTALLED")
        return False


def check_file_exists(file_path, description):
    """Check if file exists"""
    if Path(file_path).exists():
        print(f"  {GREEN}✓{RESET} {description}: {file_path}")
        return True
    else:
        print(f"  {RED}✗{RESET} {description}: {file_path} NOT FOUND")
        return False


def main():
    """Run all verification checks"""
    print_header("🔍 TEAMS BOT SETUP VERIFICATION")

    all_checks_passed = True

    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        env_file = Path(__file__).parent / '.env'
        if env_file.exists():
            load_dotenv(env_file)
            print(f"{GREEN}✓{RESET} Loaded environment from .env file\n")
        else:
            print(f"{YELLOW}⚠{RESET}  No .env file found. Using system environment variables.\n")
    except ImportError:
        print(f"{YELLOW}⚠{RESET}  python-dotenv not installed. Using system environment variables.\n")

    # Check required environment variables
    print_header("Environment Variables")

    required_vars = [
        "MICROSOFT_APP_ID",
        "MICROSOFT_APP_PASSWORD",
        "ANTHROPIC_API_KEY"
    ]

    optional_vars = [
        "MICROSOFT_APP_TYPE",
        "MICROSOFT_APP_TENANTID",
        "BOT_ENDPOINT_PORT",
        "BOT_ENDPOINT_HOST"
    ]

    print("Required:")
    for var in required_vars:
        if not check_env_var(var, required=True):
            all_checks_passed = False

    print("\nOptional:")
    for var in optional_vars:
        check_env_var(var, required=False)

    # Check Python dependencies
    print_header("Python Dependencies")

    dependencies = [
        ("botbuilder.core", "botbuilder-core"),
        ("botbuilder.schema", "botbuilder-schema"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("aiohttp", "aiohttp"),
        ("dotenv", "python-dotenv"),
    ]

    for module, package in dependencies:
        if not check_dependency(module, package):
            all_checks_passed = False

    # Check for Claude Agent SDK
    print("\nClaude Agent SDK:")
    try:
        from claude_agent_sdk import ClaudeSDKClient
        print(f"  {GREEN}✓{RESET} claude-agent-sdk")
    except ImportError:
        print(f"  {RED}✗{RESET} claude-agent-sdk: NOT INSTALLED")
        all_checks_passed = False

    # Check required files
    print_header("Required Files")

    base_dir = Path(__file__).parent
    files_to_check = [
        (base_dir / "teams_bot.py", "Main bot server"),
        (base_dir / "teams_handler.py", "Message handler"),
        (base_dir / "teams_adapter.py", "Bot adapter"),
        (base_dir / "teams_config.py", "Configuration"),
        (base_dir / "agent.py", "Claude agent"),
        (base_dir / "teams_app" / "manifest.json", "Teams app manifest"),
    ]

    for file_path, description in files_to_check:
        if not check_file_exists(file_path, description):
            all_checks_passed = False

    # Check Teams app manifest
    print_header("Teams App Manifest")

    manifest_path = base_dir / "teams_app" / "manifest.json"
    if manifest_path.exists():
        try:
            import json
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            # Check if App ID is configured
            app_id = manifest.get('id', '')
            if '{{MICROSOFT_APP_ID}}' in app_id:
                print(f"  {YELLOW}⚠{RESET}  manifest.json contains placeholder {{{{MICROSOFT_APP_ID}}}}")
                print(f"      Update with actual App ID before creating package")
            else:
                print(f"  {GREEN}✓{RESET} App ID configured in manifest")

            # Check for icons
            color_icon = base_dir / "teams_app" / "color.png"
            outline_icon = base_dir / "teams_app" / "outline.png"

            if color_icon.exists():
                print(f"  {GREEN}✓{RESET} color.png (192x192) exists")
            else:
                print(f"  {YELLOW}⚠{RESET}  color.png (192x192) not found - create before packaging")

            if outline_icon.exists():
                print(f"  {GREEN}✓{RESET} outline.png (32x32) exists")
            else:
                print(f"  {YELLOW}⚠{RESET}  outline.png (32x32) not found - create before packaging")

        except json.JSONDecodeError:
            print(f"  {RED}✗{RESET} manifest.json is invalid JSON")
            all_checks_passed = False
        except Exception as e:
            print(f"  {RED}✗{RESET} Error reading manifest: {e}")

    # Configuration check
    print_header("Configuration Check")

    try:
        from teams_config import TeamsConfig
        TeamsConfig.validate()
        print(f"  {GREEN}✓{RESET} Teams configuration is valid")
    except ValueError as e:
        print(f"  {RED}✗{RESET} Configuration error: {e}")
        all_checks_passed = False
    except Exception as e:
        print(f"  {RED}✗{RESET} Error loading configuration: {e}")
        all_checks_passed = False

    # Summary
    print_header("Summary")

    if all_checks_passed:
        print(f"{GREEN}✅ All critical checks passed!{RESET}")
        print("\n📋 Next steps:")
        print("  1. Run the bot: python teams_bot.py")
        print("  2. Expose with ngrok: ngrok http 3978")
        print("  3. Update Azure Bot messaging endpoint")
        print("  4. Install Teams app and test")
        print("\nSee TEAMS_QUICKSTART.md for detailed instructions.")
        return 0
    else:
        print(f"{RED}❌ Some checks failed!{RESET}")
        print("\n🔧 To fix:")
        print("  1. Install missing dependencies: pip install -r requirements.txt")
        print("  2. Configure environment variables in .env file")
        print("  3. See TEAMS_DEPLOYMENT.md for setup instructions")
        return 1


if __name__ == "__main__":
    sys.exit(main())
