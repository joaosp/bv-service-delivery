"""
Microsoft Teams Bot Framework Adapter

Handles authentication, activity processing, and integration with Azure Bot Service
"""

from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity
from teams_config import TeamsConfig


def create_bot_adapter() -> BotFrameworkAdapter:
    """
    Create and configure Bot Framework adapter

    Returns:
        Configured BotFrameworkAdapter instance
    """
    # Validate configuration
    TeamsConfig.validate()

    # Create adapter settings
    settings = BotFrameworkAdapterSettings(
        app_id=TeamsConfig.APP_ID,
        app_password=TeamsConfig.APP_PASSWORD,
        # For SingleTenant bots, set the tenant ID
        channel_auth_tenant=TeamsConfig.APP_TENANTID if TeamsConfig.APP_TYPE == "SingleTenant" else None
    )

    # Create adapter with settings
    adapter = BotFrameworkAdapter(settings)

    # Error handler for the adapter
    async def on_error(context, error):
        """
        Handle errors that occur during bot execution

        Args:
            context: Turn context when error occurred
            error: Exception that was raised
        """
        print(f"\n[Bot Error] {error}", flush=True)
        import traceback
        traceback.print_exc()

        # Send a message to the user
        await context.send_activity("❌ Sorry, an error occurred while processing your request. Please try again.")

    adapter.on_turn_error = on_error

    return adapter


# Create singleton adapter instance
bot_adapter = create_bot_adapter()
