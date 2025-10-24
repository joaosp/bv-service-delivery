# Microsoft Teams Bot Deployment Guide

Complete guide for deploying the BV Provisioning Agent as a Microsoft Teams bot using the Bot Framework.

## Architecture Overview

```
Microsoft Teams Client
        ↓
Microsoft Teams Service
        ↓
Azure Bot Service (Bot Connector)
        ↓
Your Bot Server (FastAPI)
        ↓
Teams Activity Handler
        ↓
BVProvisioningAgent (Claude SDK)
```

---

## Prerequisites

1. **Azure Subscription** - For Bot Service registration
2. **Microsoft 365 Account** - With Teams access
3. **Python 3.10+** - For running the bot server
4. **Public HTTPS Endpoint** - Azure App Service, ngrok, or similar

---

## Step 1: Azure Bot Service Registration

### Create Bot Resource

1. Go to [Azure Portal](https://portal.azure.com)
2. Click **Create a resource** → Search for **"Azure Bot"**
3. Click **Create**

### Configure Bot Registration

**Basic Settings:**
- **Bot handle**: `bv-provisioning-agent` (unique name)
- **Subscription**: Your Azure subscription
- **Resource group**: Create new or use existing
- **Pricing tier**: F0 (Free) for testing, S1 for production

**Microsoft App ID:**
- Select **"Create new Microsoft App ID"**
- **Type of App**: Multi-Tenant (or Single Tenant if organization-only)
- **Creation type**: **"Create new Microsoft App ID"**

### Get Credentials

After creation:

1. Go to your Bot resource → **Configuration**
2. Copy the **Microsoft App ID** (save this)
3. Click **Manage** next to Microsoft App ID
4. Go to **Certificates & secrets**
5. Click **New client secret**
   - Description: "BV Provisioning Bot"
   - Expires: 24 months (or as per policy)
6. **Copy the secret VALUE immediately** (you won't see it again)

---

## Step 2: Local Development Setup

### Install Dependencies

```bash
cd agents/bv-provisioning-agent

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install new dependencies
pip install -r requirements.txt
```

### Configure Environment Variables

Create or update `.env` file:

```bash
# Existing variables
ANTHROPIC_API_KEY=your_claude_api_key

# NEW - Microsoft Teams Bot Variables
MICROSOFT_APP_ID=your-app-id-from-azure
MICROSOFT_APP_PASSWORD=your-app-secret-from-azure
MICROSOFT_APP_TYPE=MultiTenant
# MICROSOFT_APP_TENANTID=your-tenant-id  # Only for SingleTenant

# Bot server configuration
BOT_ENDPOINT_PORT=3978
BOT_ENDPOINT_HOST=0.0.0.0
```

### Test Locally with ngrok

1. **Install ngrok** (if not already):
   ```bash
   # macOS
   brew install ngrok

   # Or download from https://ngrok.com/download
   ```

2. **Start the bot server**:
   ```bash
   python teams_bot.py
   ```

   Should see:
   ```
   🤖 BV PROVISIONING TEAMS BOT
   Endpoint: http://0.0.0.0:3978/api/messages
   Waiting for Teams messages...
   ```

3. **Start ngrok** (in a new terminal):
   ```bash
   ngrok http 3978
   ```

   Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

4. **Update Azure Bot messaging endpoint**:
   - Go to Azure Portal → Your Bot → **Configuration**
   - **Messaging endpoint**: `https://abc123.ngrok.io/api/messages`
   - Click **Apply**

---

## Step 3: Enable Teams Channel

1. Go to Azure Portal → Your Bot → **Channels**
2. Click **Microsoft Teams** icon
3. Configure:
   - **Messaging**: Enable
   - **Calling**: Not required
   - Click **Apply**
4. Click **Agree** to Terms of Service
5. Teams channel is now enabled ✅

---

## Step 4: Create Teams App Package

### Prepare Icons

Create two icon files in `teams_app/` directory:

**color.png** (192x192 pixels):
- Use BroadVoice logo or a robot icon
- PNG format with brand colors

**outline.png** (32x32 pixels):
- Simple white outline icon
- PNG with transparent background

You can use tools like Canva, Figma, or any image editor.

### Update Manifest

Edit `teams_app/manifest.json`:

```bash
cd teams_app
# Replace placeholder with your actual App ID
sed -i '' 's/{{MICROSOFT_APP_ID}}/YOUR-ACTUAL-APP-ID/g' manifest.json
```

### Create ZIP Package

```bash
# From teams_app directory
zip BVProvisioningAgent.zip manifest.json color.png outline.png
```

Verify the package:
- Contains exactly 3 files at root level
- No subdirectories
- manifest.json is valid JSON

---

## Step 5: Install Bot in Teams

### Method 1: Sideload (Personal Testing)

1. Open **Microsoft Teams** (Desktop or Web)
2. Click **Apps** in the left sidebar
3. Click **Manage your apps** (bottom left)
4. Click **Upload a custom app**
5. Select **Upload for me or my teams**
6. Choose `BVProvisioningAgent.zip`
7. Click **Add**

### Method 2: Admin Center (Organization-wide)

1. Go to [Teams Admin Center](https://admin.teams.microsoft.com)
2. Navigate to **Teams apps** → **Manage apps**
3. Click **Upload new app**
4. Upload `BVProvisioningAgent.zip`
5. Configure permissions and app policies
6. Publish to organization

---

## Step 6: Test the Bot

### Start a Chat

1. In Teams, find **BV Provisioning Agent** in your apps
2. Click **Add** or **Open**
3. Start chatting!

### Test Commands

```
/help
/status
What are the critical mandatory fields?
Extract provisioning data for opportunity 0065e00000XxxxxxAAA
```

### Check Logs

Monitor your bot server terminal for:
- Incoming messages
- Tool usage
- Errors

---

## Step 7: Production Deployment

### Option A: Azure App Service (Recommended)

1. **Create App Service**:
   ```bash
   # Login to Azure CLI
   az login

   # Create resource group (if needed)
   az group create --name bv-provisioning-rg --location eastus

   # Create App Service plan
   az appservice plan create \
     --name bv-provisioning-plan \
     --resource-group bv-provisioning-rg \
     --sku B1 \
     --is-linux

   # Create Web App
   az webapp create \
     --name bv-provisioning-bot \
     --resource-group bv-provisioning-rg \
     --plan bv-provisioning-plan \
     --runtime "PYTHON:3.10"
   ```

2. **Configure App Settings**:
   ```bash
   az webapp config appsettings set \
     --name bv-provisioning-bot \
     --resource-group bv-provisioning-rg \
     --settings \
       MICROSOFT_APP_ID="your-app-id" \
       MICROSOFT_APP_PASSWORD="your-app-secret" \
       ANTHROPIC_API_KEY="your-claude-key"
   ```

3. **Deploy Code**:
   ```bash
   # Create deployment package
   cd agents/bv-provisioning-agent
   zip -r deploy.zip . -x "*.git*" -x "*venv*" -x "*__pycache__*"

   # Deploy
   az webapp deployment source config-zip \
     --name bv-provisioning-bot \
     --resource-group bv-provisioning-rg \
     --src deploy.zip
   ```

4. **Update Azure Bot Messaging Endpoint**:
   - Go to Azure Portal → Your Bot → Configuration
   - Messaging endpoint: `https://bv-provisioning-bot.azurewebsites.net/api/messages`
   - Click Apply

### Option B: Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3978

CMD ["python", "teams_bot.py"]
```

Build and run:

```bash
docker build -t bv-provisioning-bot .
docker run -p 3978:3978 \
  -e MICROSOFT_APP_ID=your-app-id \
  -e MICROSOFT_APP_PASSWORD=your-secret \
  -e ANTHROPIC_API_KEY=your-key \
  bv-provisioning-bot
```

---

## Troubleshooting

### Bot doesn't respond to messages

**Check 1: Messaging endpoint**
- Ensure endpoint URL is HTTPS
- Verify it's publicly accessible
- Test: `curl https://your-bot-url.com/health` should return 200

**Check 2: Credentials**
- Verify `MICROSOFT_APP_ID` matches Azure Bot registration
- Ensure `MICROSOFT_APP_PASSWORD` is correct
- Check for typos or extra spaces

**Check 3: Bot server logs**
```bash
# Look for errors in terminal or App Service logs
az webapp log tail --name bv-provisioning-bot --resource-group bv-provisioning-rg
```

### Authentication errors (401 Unauthorized)

- App ID/Password mismatch
- Client secret expired (regenerate in Azure Portal)
- Multi-tenant vs Single-tenant configuration mismatch

### Bot receives messages but times out

- Claude Agent SDK queries taking too long
- Increase timeout in `teams_config.py`: `AGENT_TIMEOUT = 180`
- Consider async processing for long operations

### "App validation failed" when uploading

- Check `manifest.json` syntax (use jsonlint.com)
- Verify icon dimensions (192x192 and 32x32)
- Ensure App ID is correct in manifest

### Messages not showing in Teams

- Check conversation history in `conversation_store`
- Verify response is being sent (check logs)
- Test with simple echo response first

---

## Monitoring & Maintenance

### Application Insights (Azure)

Enable monitoring:

```bash
az webapp config appsettings set \
  --name bv-provisioning-bot \
  --resource-group bv-provisioning-rg \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY="your-key"
```

### Logging

Add structured logging to `teams_handler.py`:

```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Received message from {user_name}: {user_message}")
```

### Health Checks

Monitor these endpoints:
- `/` - Basic status
- `/health` - Health check for Azure

Set up alerts for downtime or errors.

---

## Security Best Practices

1. **Rotate secrets regularly** - Update client secrets every 6-12 months
2. **Use Azure Key Vault** - Store secrets securely (not in env vars)
3. **Enable HTTPS only** - Never use HTTP for messaging endpoint
4. **Validate requests** - Bot Framework adapter validates JWT tokens
5. **Rate limiting** - Implement if needed to prevent abuse
6. **Audit logs** - Track all provisioning data access

---

## Next Steps

1. **Add Adaptive Cards** - Rich formatted messages
2. **Implement proactive messaging** - Send notifications to users
3. **Add authentication** - Azure AD SSO for sensitive operations
4. **Persistent storage** - Use Azure Table Storage or Cosmos DB for conversation history
5. **CI/CD pipeline** - Automate deployment with GitHub Actions

---

## Resources

- [Bot Framework Documentation](https://learn.microsoft.com/en-us/azure/bot-service/)
- [Teams App Development](https://learn.microsoft.com/en-us/microsoftteams/platform/)
- [Azure Bot Service Pricing](https://azure.microsoft.com/en-us/pricing/details/bot-services/)
- [Bot Framework SDK (Python)](https://github.com/microsoft/botbuilder-python)

---

## Support

For issues with:
- **Teams bot integration**: Check this guide first, then Azure Bot Service docs
- **Claude Agent SDK**: See agent.py and Claude SDK documentation
- **Salesforce data extraction**: See tools.py and existing agent documentation
