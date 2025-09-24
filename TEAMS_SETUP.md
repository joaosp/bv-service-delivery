# Microsoft Teams Transcript Integration Setup

This document explains how to configure Microsoft Teams transcript extraction for the BroadVoice Service Automation system.

## Prerequisites

1. **Azure AD App Registration**: You need an Azure Active Directory application with proper permissions
2. **Microsoft Graph API Access**: Application must have OnlineMeetingTranscript.Read.All permissions
3. **Teams Meeting Access**: Service account must have access to the Teams meetings

## Azure AD App Setup

### 1. Create Azure AD App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Fill in:
   - **Name**: `BroadVoice Service Automation`
   - **Supported account types**: Accounts in this organizational directory only
   - **Redirect URI**: Not needed for this use case
5. Click **Register**

### 2. Configure API Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. Choose **Application permissions**
5. Search for and add:
   - `OnlineMeetingTranscript.Read.All`
   - `OnlineMeeting.Read.All` (if you need meeting metadata)
6. Click **Grant admin consent for [Your Organization]**

### 3. Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Add description: `BroadVoice Transcript Access`
4. Choose expiration (recommended: 24 months)
5. Click **Add**
6. **Important**: Copy the secret value immediately (it won't be shown again)

### 4. Note Required Values

Copy these values from your app registration:
- **Application (client) ID**: From the Overview page
- **Directory (tenant) ID**: From the Overview page  
- **Client secret**: From the previous step

## Environment Configuration

Create environment variables with your Azure credentials:

```bash
# Set in your shell profile (.bashrc, .zshrc, etc.) or runtime environment
export AZURE_CLIENT_ID="your-application-client-id"
export AZURE_CLIENT_SECRET="your-client-secret-value"  
export AZURE_TENANT_ID="your-directory-tenant-id"
```

### For Development/Testing

You can also create a `.env` file in the project root:

```env
AZURE_CLIENT_ID=your-application-client-id
AZURE_CLIENT_SECRET=your-client-secret-value
AZURE_TENANT_ID=your-directory-tenant-id
```

## Application Access Policy (Required)

Since the API uses application permissions, you need to create an application access policy to authorize the app to access meetings on behalf of users.

### PowerShell Setup

1. Install Microsoft Teams PowerShell module:
   ```powershell
   Install-Module -Name MicrosoftTeams
   ```

2. Connect to Microsoft Teams:
   ```powershell
   Connect-MicrosoftTeams
   ```

3. Create application access policy:
   ```powershell
   New-CsApplicationAccessPolicy -Identity "BroadVoice-Transcript-Policy" -AppIds "your-application-client-id" -Description "Allow BroadVoice app to access meeting transcripts"
   ```

4. Assign policy to users who organize meetings:
   ```powershell
   Grant-CsApplicationAccessPolicy -PolicyName "BroadVoice-Transcript-Policy" -Identity "user@company.com"
   ```

## Testing the Integration

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables** (as shown above)

3. **Run a test extraction**:
   ```bash
   python extract_opportunity_data_modular.py 006Pq00000Qb93lIAB
   ```

4. **Check for Teams transcripts** in the output:
   - Look for `📞 Step 5: Extracting Call Transcripts` section
   - VideoCall records should be found
   - Teams transcripts should be downloaded to `transcripts/` folder

## Troubleshooting

### Common Issues

1. **Authentication Failure**:
   - Verify Azure credentials are set correctly
   - Check app registration permissions
   - Ensure admin consent was granted

2. **Meeting Not Found**:
   - Verify the meeting organizer has the application access policy
   - Check if meeting has expired (transcripts have retention periods)
   - Confirm meeting was recorded and transcribed

3. **Permission Denied**:
   - Verify application access policy is applied to meeting organizer
   - Check if the app has proper Graph API permissions
   - Ensure the service account has access to the meeting

### Debug Mode

To enable detailed logging, add this to your environment:

```bash
export PYTHON_LOG_LEVEL=DEBUG
```

### API Limits

- Microsoft Graph has rate limits for transcript access
- Large meetings may take time to process
- Consider implementing retry logic for production use

## Production Considerations

1. **Security**:
   - Store secrets in Azure Key Vault or similar secure storage
   - Use managed identities when possible
   - Regular secret rotation

2. **Reliability**:
   - Implement retry logic with exponential backoff
   - Handle API rate limits gracefully  
   - Monitor API usage and costs

3. **Compliance**:
   - Ensure transcript access complies with company policies
   - Consider data retention requirements
   - Implement audit logging for transcript access

## API Reference

- [Microsoft Graph OnlineMeeting API](https://docs.microsoft.com/en-us/graph/api/resources/onlinemeeting)
- [Microsoft Graph CallTranscript API](https://docs.microsoft.com/en-us/graph/api/resources/calltranscript)
- [Application Access Policies](https://docs.microsoft.com/en-us/graph/cloud-communication-online-meeting-application-access-policy)