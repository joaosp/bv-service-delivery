#!/usr/bin/env python3
"""
Microsoft Teams Bot Server

FastAPI server that receives activities from Azure Bot Service and processes them
using the BV Provisioning Agent (Claude Agent SDK)

Usage:
    python teams_bot.py

    # Or with uvicorn directly:
    uvicorn teams_bot:app --host 0.0.0.0 --port 3978

Environment Variables Required:
    MICROSOFT_APP_ID - Azure Bot Service App ID
    MICROSOFT_APP_PASSWORD - Azure Bot Service App Password
"""

import sys
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from botbuilder.schema import Activity
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from teams_config import TeamsConfig
from teams_adapter import bot_adapter
from teams_handler import TeamsActivityHandler

# Validate configuration before starting
try:
    TeamsConfig.validate()
except ValueError as e:
    print(f"❌ Configuration error: {e}")
    print("\nPlease set the following environment variables:")
    print("  - MICROSOFT_APP_ID")
    print("  - MICROSOFT_APP_PASSWORD")
    sys.exit(1)

# Create FastAPI app
app = FastAPI(
    title="BV Provisioning Teams Bot",
    description="Microsoft Teams bot for BroadVoice provisioning workflows",
    version="1.0.0"
)

# Create bot handler
bot_handler = TeamsActivityHandler()


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "bot": "BV Provisioning Agent",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check for Azure App Service"""
    return {"status": "healthy"}


@app.post(TeamsConfig.MESSAGES_ENDPOINT)
async def messages(request: Request):
    """
    Main endpoint for receiving activities from Azure Bot Service

    This endpoint receives POST requests from the Azure Bot Service containing
    Activity objects in JSON format. The adapter handles authentication and
    routes the activity to the bot handler.
    """
    # Get the request body
    body = await request.json()

    # Create Activity object from request
    activity = Activity().deserialize(body)

    # Get authorization header for authentication
    auth_header = request.headers.get("Authorization", "")

    # Process the activity using the adapter
    # The adapter handles JWT validation and routes to bot_handler
    async def aux_func(turn_context):
        await bot_handler.on_turn(turn_context)

    try:
        await bot_adapter.process_activity(activity, auth_header, aux_func)
        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error processing activity: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": str(e)}
        )


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("🤖 BV PROVISIONING TEAMS BOT")
    print("=" * 70)
    print(f"Endpoint: http://{TeamsConfig.HOST}:{TeamsConfig.PORT}{TeamsConfig.MESSAGES_ENDPOINT}")
    print(f"App ID: {TeamsConfig.APP_ID[:8]}..." if TeamsConfig.APP_ID else "App ID: Not configured")
    print("=" * 70)
    print("\nWaiting for Teams messages...\n")

    uvicorn.run(
        app,
        host=TeamsConfig.HOST,
        port=TeamsConfig.PORT,
        log_level="info"
    )
