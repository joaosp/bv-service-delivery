# Microsoft Teams App Package

This directory contains the Teams app manifest and resources needed to install the BV Provisioning Agent bot in Microsoft Teams.

## Files Required

1. **manifest.json** - App configuration (already created)
2. **color.png** - Color icon (192x192 pixels)
3. **outline.png** - Outline icon (32x32 pixels)

## Creating Icons

### Color Icon (192x192)
- Size: 192x192 pixels
- Format: PNG
- Usage: Main app icon in Teams
- Recommended: BroadVoice logo or robot icon with brand colors

### Outline Icon (32x32)
- Size: 32x32 pixels
- Format: PNG with transparent background
- Color: White outline
- Usage: Small icon in Teams interface

You can create these icons using:
- **Canva** - https://www.canva.com (free templates)
- **Figma** - https://www.figma.com
- **GIMP** - Free image editor
- **Any image editing tool** that can export PNG

## Configuring the Manifest

Before creating the app package, replace `{{MICROSOFT_APP_ID}}` in `manifest.json` with your actual Azure Bot Service App ID:

```bash
# Replace placeholder with your App ID
sed -i '' 's/{{MICROSOFT_APP_ID}}/YOUR-ACTUAL-APP-ID/g' manifest.json
```

Or manually edit `manifest.json` and replace both occurrences of `{{MICROSOFT_APP_ID}}`.

## Creating the App Package

Once you have all three files (manifest.json, color.png, outline.png):

1. **Zip the files**:
   ```bash
   cd teams_app
   zip -r BVProvisioningAgent.zip manifest.json color.png outline.png
   ```

2. **Verify the package**:
   - The ZIP file should contain exactly 3 files at the root level
   - No subdirectories
   - manifest.json must be valid JSON

## Installing in Teams

### Method 1: Sideload in Teams Desktop/Web

1. Open Microsoft Teams
2. Click **Apps** in the left sidebar
3. Click **Manage your apps** (bottom left)
4. Click **Upload a custom app** → **Upload for me or my teams**
5. Select the `BVProvisioningAgent.zip` file
6. Click **Add** to install

### Method 2: Teams Admin Center (Organization-wide)

1. Go to [Teams Admin Center](https://admin.teams.microsoft.com)
2. Navigate to **Teams apps** → **Manage apps**
3. Click **Upload new app**
4. Upload the `BVProvisioningAgent.zip` file
5. Configure app permissions and policies as needed

## Testing the Bot

After installation:

1. Open the app in Teams
2. Start a chat with the bot
3. Try commands:
   - `/help` - Show available commands
   - `/status` - Check bot status
   - Ask a question: "What are the critical mandatory fields?"

## Troubleshooting

### "App validation failed"
- Ensure all required fields in manifest.json are filled
- Verify icon dimensions are correct (192x192 and 32x32)
- Check that JSON is valid (use jsonlint.com)

### "Bot doesn't respond"
- Verify Azure Bot Service messaging endpoint is configured
- Check that the bot server is running and accessible
- Review bot server logs for errors
- Ensure MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD are correct

### "Authentication failed"
- Double-check App ID matches in manifest.json and Azure Bot
- Verify App Password is correct in environment variables
- Ensure bot is registered in Azure Bot Service

## Updating the App

To update the app after making changes:

1. Increment version in manifest.json (e.g., "1.0.0" → "1.0.1")
2. Recreate the ZIP package
3. In Teams: **Apps** → **Manage your apps** → Click the app → **Update**
4. Upload the new ZIP file

## Resources

- [Teams App Manifest Schema](https://learn.microsoft.com/en-us/microsoftteams/platform/resources/schema/manifest-schema)
- [App Icons Guidelines](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/apps-package)
- [Upload Custom Apps](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/deploy-and-publish/apps-upload)
