# Microsoft Teams Transcript Access - Per-User Setup Guide

## Overview
This guide configures **per-user access** to Teams meeting transcripts instead of organization-wide access. The app will only access meetings organized by specifically authorized users.

## Architecture
- **Access Model**: Per-user application access policy
- **Permissions**: Application permissions (unattended access)
- **Scope**: Limited to meetings organized by authorized users only

---

## Step 1: Azure AD App Registration - Add Permission

### Add OnlineMeetings.Read.All Permission

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to: **Azure Active Directory** → **App registrations** → Select your app
3. Go to **API permissions** → **Add a permission**
4. Select **Microsoft Graph** → **Application permissions**
5. Search for and add: `OnlineMeetings.Read.All`
6. Click **Grant admin consent for [your tenant]** ✅

### Verify Current Permissions
Your app should now have:
- ✅ `OnlineMeetings.Read.All` (Application) - Access meeting metadata
- ✅ `OnlineMeetingTranscript.Read.All` (Application) - Access transcript content
- ✅ `User.Read.All` (Application) - Resolve user emails (for better logging)

---

## Step 2: PowerShell - Create Application Access Policy

### Prerequisites
Install Teams PowerShell module:
```powershell
Install-Module -Name MicrosoftTeams -Force -AllowClobber
```

### Connect to Teams
```powershell
Connect-MicrosoftTeams
```

### Get Your Azure AD App Client ID
From your `.env` file or Azure Portal:
```bash
# Your AZURE_CLIENT_ID value
```

### Create the Access Policy
```powershell
# Create policy for BV provisioning app
New-CsApplicationAccessPolicy `
    -Identity "BV-Provisioning-Transcript-Access" `
    -AppIds "<YOUR_AZURE_CLIENT_ID>" `
    -Description "Allows BV provisioning app to access meeting transcripts for authorized sales users"
```

---

## Step 3: Grant Access to Specific Users

### Option A: Grant to Individual User (Alejandro De La Hoz - Test)

```powershell
# Grant access for Alejandro De La Hoz (test user)
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "alejandro@broadvoice.com"

# Or use Azure AD Object ID:
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "<alejandro-azure-ad-object-id>"
```

### Option B: Grant to Multiple Users
```powershell
# List of authorized users
$authorizedUsers = @(
    "alejandro@broadvoice.com",
    "user2@broadvoice.com",
    "user3@broadvoice.com"
)

foreach ($user in $authorizedUsers) {
    Grant-CsApplicationAccessPolicy `
        -PolicyName "BV-Provisioning-Transcript-Access" `
        -Identity $user
    Write-Host "✅ Granted access to: $user"
}
```

### Option C: Grant to Azure AD Group (Recommended for Scale)
```powershell
# Get group ID from Azure AD
$salesGroupId = "<azure-ad-group-id>"  # e.g., Sales Team group

Grant-CsApplicationAccessPolicy `
    -Group $salesGroupId `
    -PolicyName "BV-Provisioning-Transcript-Access"

Write-Host "✅ Granted access to entire group"
```

---

## Step 4: Verify Policy Configuration

### List All Application Access Policies
```powershell
Get-CsApplicationAccessPolicy
```

### Check User's Assigned Policy
```powershell
Get-CsOnlineUser -Identity "alejandro@broadvoice.com" |
    Select-Object DisplayName, ApplicationAccessPolicy
```

### Test Access (After 30 min wait)
```bash
cd /Users/jcamarate/dev/bv-service-delivery/agents/bv-provisioning-agent
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
```

---

## Step 5: Understanding the Access Model

### What Gets Accessed
✅ **Accessible**: Meetings **organized by** authorized users
❌ **Not accessible**: Meetings organized by other users
❌ **Not accessible**: Meetings where authorized user is just a participant

### Example Scenarios

**Scenario 1: Alejandro organizes meeting**
- Meeting ID: `abc123`
- Organizer: `alejandro@broadvoice.com` ✅ (in policy)
- Result: ✅ App can access transcript

**Scenario 2: Other user organizes meeting**
- Meeting ID: `xyz789`
- Organizer: `other-user@broadvoice.com` ❌ (not in policy)
- Result: ❌ App receives clear error message with instructions

---

## Error Messages

### Code Now Provides Clear Guidance

#### Error 1: Missing Permission
```
Permission Error: Missing 'OnlineMeetings.Read.All' application permission.
  Add this permission in Azure AD App Registration and grant admin consent.
```
**Solution**: Complete Step 1

#### Error 2: Access Policy Not Covering User
```
Access Policy Error - Organizer: alejandro@broadvoice.com
  The application access policy doesn't cover this user.
  To grant access, run:
  Grant-CsApplicationAccessPolicy -PolicyName "<PolicyName>" -Identity "alejandro@broadvoice.com"
  Note: Policy changes take up to 30 minutes to propagate.
```
**Solution**: Complete Step 3 for this specific user

#### Error 3: Access Denied (Generic)
```
Access Denied (403) for organizer user@domain.com: [detailed error message]
```
**Solution**: Check Azure AD permissions and policy configuration

---

## Testing Checklist

### Test with Opportunity 006Pq00000WKi7LIAT

```bash
cd /Users/jcamarate/dev/bv-service-delivery/agents/bv-provisioning-agent
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
```

**Expected Output:**
1. ✅ Resolves organizer email: "Alejandro De La Hoz (alejandro@broadvoice.com)"
2. ✅ Access policy check passes
3. ✅ Meeting found
4. ✅ Transcript extracted

**If you see errors:**
- Wait 30 minutes after granting policy (propagation time)
- Verify Alejandro is the meeting organizer (check VideoCall.VendorMeetingKey)
- Check Azure AD permissions have admin consent

---

## Code Changes Summary

### New Methods in `salesforce_extractors/teams_transcript.py`

1. **`resolve_user_email(user_id)`** - Converts Azure AD GUID to email
2. **`check_access_policy(organizer_id)`** - Pre-validates access before attempting extraction
3. **Enhanced error handling** - Distinguishes permission vs access policy issues

### Key Improvements
- ✅ Shows organizer email in logs (not just GUID)
- ✅ Fails fast with clear error messages
- ✅ Provides exact PowerShell commands to fix issues
- ✅ No changes needed to calling code

---

## Adding More Users

### When a New Sales Rep Needs Access

```powershell
# Single command to add new user
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "newrep@broadvoice.com"
```

Wait 30 minutes, then test!

---

## Troubleshooting

### Policy Not Working After 30 Minutes
```powershell
# Remove and re-grant policy
Grant-CsApplicationAccessPolicy `
    -PolicyName $null `
    -Identity "user@broadvoice.com"

Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "user@broadvoice.com"
```

### Check Who Has the Policy
```powershell
Get-CsOnlineUser | Where-Object {$_.ApplicationAccessPolicy -eq "BV-Provisioning-Transcript-Access"} |
    Select-Object DisplayName, UserPrincipalName
```

### Remove Access from User
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName $null `
    -Identity "user@broadvoice.com"
```

---

## Security Benefits

### Why This is Better Than Organization-Wide Access

| Aspect | Organization-Wide | Per-User Policy |
|--------|------------------|-----------------|
| **Access Scope** | All meetings in tenant | Only specific users' meetings |
| **Security Risk** | High - accesses everything | Low - minimal necessary access |
| **Audit Trail** | Hard to track who authorized | Clear policy assignments |
| **Compliance** | May violate data policies | Meets least-privilege principle |
| **User Privacy** | All meetings exposed | Only business meetings accessed |

---

## Next Steps

1. ✅ Complete Azure AD permission setup (Step 1)
2. ✅ Create PowerShell access policy (Step 2)
3. ✅ Grant to Alejandro for testing (Step 3)
4. ⏱️ Wait 30 minutes
5. 🧪 Run test: `python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT`
6. 📈 Expand to other sales team members as needed

---

## Support

If you encounter issues:
1. Check error messages - they now include exact fix instructions
2. Verify 30-minute propagation window
3. Confirm user is meeting organizer (not just participant)
4. Review Azure AD app permissions have admin consent
