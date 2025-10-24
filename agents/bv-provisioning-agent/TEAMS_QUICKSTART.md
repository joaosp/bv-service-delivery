# Teams Bot Quick Start Guide

Get the BV Provisioning Agent running in Microsoft Teams in under 30 minutes.

## TL;DR

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export MICROSOFT_APP_ID="your-app-id"
export MICROSOFT_APP_PASSWORD="your-app-secret"

# 3. Run bot server
python teams_bot.py

# 4. Expose with ngrok (for local dev)
ngrok http 3978

# 5. Configure Azure Bot messaging endpoint with ngrok URL
# 6. Install Teams app and chat with your bot!
```

---

## Detailed Quick Start

### 1. Azure Bot Registration (5 minutes)

1. Go to [Azure Portal](https://portal.azure.com)
2. Create **Azure Bot** resource
3. Copy **App ID** and create **Client Secret**
4. Enable **Teams Channel**

👉 See [TEAMS_DEPLOYMENT.md](TEAMS_DEPLOYMENT.md#step-1-azure-bot-service-registration) for detailed steps

### 2. Configure Environment (2 minutes)

Edit `.env` file:

```bash
# Required
MICROSOFT_APP_ID=your-app-id-here
MICROSOFT_APP_PASSWORD=your-client-secret-here
ANTHROPIC_API_KEY=your-claude-api-key

# Optional
BOT_ENDPOINT_PORT=3978
MICROSOFT_APP_TYPE=MultiTenant
```

### 3. Install Dependencies (2 minutes)

```bash
cd agents/bv-provisioning-agent
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run Bot Locally (1 minute)

```bash
python teams_bot.py
```

Expected output:
```
🤖 BV PROVISIONING TEAMS BOT
======================================================================
Endpoint: http://0.0.0.0:3978/api/messages
App ID: 12345678...
======================================================================

Waiting for Teams messages...
```

### 5. Expose with ngrok (2 minutes)

**Install ngrok:**
```bash
# macOS
brew install ngrok

# Windows - download from ngrok.com
```

**Run ngrok:**
```bash
ngrok http 3978
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok-free.app`)

### 6. Update Azure Bot Endpoint (1 minute)

1. Azure Portal → Your Bot → **Configuration**
2. **Messaging endpoint**: `https://your-ngrok-url.ngrok-free.app/api/messages`
3. Click **Save**

### 7. Create Teams App Package (5 minutes)

**Option A: Use placeholder icons (fastest)**

```bash
cd teams_app

# Create simple placeholder icons (requires ImageMagick)
convert -size 192x192 xc:blue -pointsize 72 -fill white -gravity center \
  -annotate +0+0 "BV" color.png

convert -size 32x32 xc:none -fill white -stroke white -strokewidth 2 \
  -draw "circle 16,16 16,4" outline.png

# Update manifest with your App ID
sed -i '' 's/{{MICROSOFT_APP_ID}}/YOUR-ACTUAL-APP-ID/g' manifest.json

# Create package
zip BVProvisioningAgent.zip manifest.json color.png outline.png
```

**Option B: Use custom icons**

1. Create `color.png` (192x192) and `outline.png` (32x32)
2. Update `manifest.json` with your App ID
3. Zip files: `zip BVProvisioningAgent.zip manifest.json color.png outline.png`

### 8. Install in Teams (2 minutes)

1. Open Microsoft Teams
2. Click **Apps** → **Manage your apps** → **Upload a custom app**
3. Upload `BVProvisioningAgent.zip`
4. Click **Add**

### 9. Test! (1 minute)

Start a chat and try:

```
/help
```

```
What are the critical mandatory fields?
```

```
Extract provisioning data for opportunity 0065e00000ABC123XYZ
```

---

## Testing Checklist

- [ ] Bot responds to `/help` command
- [ ] Bot responds to `/status` command
- [ ] Bot can answer general questions about provisioning
- [ ] Bot can query Salesforce (if credentials configured)
- [ ] Conversation history works (ask follow-up questions)
- [ ] Bot handles errors gracefully

---

## Common Issues

### "Bot doesn't respond"

**Fix:**
1. Check bot server is running (`python teams_bot.py`)
2. Verify ngrok is running and URL is HTTPS
3. Confirm messaging endpoint in Azure matches ngrok URL
4. Check bot server logs for errors

### "Authentication failed"

**Fix:**
1. Verify `MICROSOFT_APP_ID` in `.env` matches Azure Bot
2. Ensure `MICROSOFT_APP_PASSWORD` is the secret VALUE (not ID)
3. Check for typos or extra spaces in environment variables

### "App validation failed"

**Fix:**
1. Validate `manifest.json` at [jsonlint.com](https://jsonlint.com)
2. Ensure icons are exactly 192x192 and 32x32 pixels
3. Confirm App ID in manifest matches Azure Bot

### "Request timed out"

**Fix:**
1. Increase timeout: Edit `teams_config.py` → `AGENT_TIMEOUT = 180`
2. Simplify your query
3. Check Claude API is responding

---

## Next Steps

### For Development
- Set up continuous development with `--reload`:
  ```bash
  uvicorn teams_bot:app --host 0.0.0.0 --port 3978 --reload
  ```

### For Production
- Deploy to Azure App Service (see [TEAMS_DEPLOYMENT.md](TEAMS_DEPLOYMENT.md#step-7-production-deployment))
- Enable Application Insights for monitoring
- Set up CI/CD pipeline

### Enhancements
- Add Adaptive Cards for rich messages
- Implement proactive notifications
- Add user authentication with Azure AD
- Store conversation history in database

---

## File Structure

```
agents/bv-provisioning-agent/
├── teams_bot.py              # Main FastAPI server ⭐
├── teams_handler.py          # Message processing logic
├── teams_adapter.py          # Bot Framework adapter
├── teams_config.py           # Configuration
├── agent.py                  # Existing Claude agent
├── requirements.txt          # Dependencies (updated)
└── teams_app/                # Teams app package
    ├── manifest.json         # App configuration
    ├── color.png            # 192x192 icon
    ├── outline.png          # 32x32 icon
    └── README.md            # Package documentation
```

---

## Resources

- **Full Deployment Guide**: [TEAMS_DEPLOYMENT.md](TEAMS_DEPLOYMENT.md)
- **Bot Framework Docs**: https://learn.microsoft.com/azure/bot-service/
- **Teams Platform**: https://learn.microsoft.com/microsoftteams/platform/
- **ngrok**: https://ngrok.com/docs

---

## Help

**Error messages?** Check bot server terminal for detailed logs

**Still stuck?** See troubleshooting section in [TEAMS_DEPLOYMENT.md](TEAMS_DEPLOYMENT.md#troubleshooting)

**Need to understand the code?** Read the inline comments in `teams_handler.py`
