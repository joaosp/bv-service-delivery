# IT Configuration Checklist - Teams Transcript Access

## Issue Found
Test returned: **403 - "No application access policy found for this app"**

This means permissions are granted but the Application Access Policy is not configured or not granted to the meeting organizer.

---

## Part 1: Verify Azure AD Permissions (Azure Portal)

### Go to: Azure Portal → App Registrations → [Your App] → API Permissions

**Check these 3 permissions are TYPE = "Application" (not "Delegated"):**

| Permission | Type | Status |
|------------|------|--------|
| OnlineMeetings.Read.All | ✅ **Application** | Admin consent granted |
| OnlineMeetingTranscript.Read.All | ✅ **Application** | Admin consent granted |
| User.Read | Delegated (OK) | Optional |

**If any show "Delegated" instead of "Application":**
1. Remove the permission
2. Click "Add a permission" → Microsoft Graph → **Application permissions**
3. Search and add the permission
4. Click "Grant admin consent for [tenant]"

---

## Part 2: Configure Application Access Policy (PowerShell)

### Prerequisites
```powershell
# Install Teams module if not installed
Install-Module -Name MicrosoftTeams -Force -AllowClobber

# Connect to Teams
Connect-MicrosoftTeams
```

### Step 1: Check if Policy Exists
```powershell
Get-CsApplicationAccessPolicy
```

**If you see your policy** (e.g., "BV-Provisioning-Transcript-Access"), skip to Step 3.

**If no policy exists or empty**, continue to Step 2.

---

### Step 2: Create Application Access Policy

**Get your App Client ID from Azure Portal or .env file**

```powershell
# Replace with actual client ID from Azure AD
$appClientId = "<YOUR_AZURE_CLIENT_ID>"

# Create the policy
New-CsApplicationAccessPolicy `
    -Identity "BV-Provisioning-Transcript-Access" `
    -AppIds $appClientId `
    -Description "Allows BV provisioning app to access meeting transcripts for sales team"

# Verify it was created
Get-CsApplicationAccessPolicy -Identity "BV-Provisioning-Transcript-Access"
```

---

### Step 3: Grant Policy to Meeting Organizer

**The test meeting organizer is:** Alejandro De La Hoz (adhoz@broadvoice.com)
**Azure AD User ID:** `ca926a60-508f-4c51-9778-cf87b4243784`

**Grant to email (recommended):**
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "adhoz@broadvoice.com"
```

**OR grant to Azure AD ID directly:**
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "ca926a60-508f-4c51-9778-cf87b4243784"
```

---

### Step 4: Verify Policy Assignment

```powershell
# Check Alejandro's policy assignment
Get-CsOnlineUser -Identity "adhoz@broadvoice.com" |
    Select-Object DisplayName, UserPrincipalName, ApplicationAccessPolicy

# Expected output:
# DisplayName           : Alejandro De La Hoz
# UserPrincipalName    : adhoz@broadvoice.com
# ApplicationAccessPolicy : BV-Provisioning-Transcript-Access
```

**If ApplicationAccessPolicy is blank:**
- The Grant command didn't work
- Try again with the exact email or Azure AD ID
- Check for typos

---

### Step 5: Wait for Propagation

⏱️ **IMPORTANT:** Policy changes take **up to 30 minutes** to propagate.

After granting:
- ✅ Wait 30 minutes
- ✅ Then run test again

---

## Part 3: Test Configuration

**After 30 minutes, test should succeed:**

```bash
cd /Users/jcamarate/dev/bv-service-delivery/agents/bv-provisioning-agent
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
```

**Expected success output:**
```
✅ Authenticated with Microsoft Graph
✅ Extracting transcript for organizer: adhoz@broadvoice.com
✅ Access policy check passed
✅ Found meeting: Design Call | 37603...
✅ Found transcripts
✅ Downloaded transcript content
```

**If still fails with 403:**
- Double-check policy name matches in Grant command
- Verify user identity is correct (try both email and Azure AD ID)
- Wait longer (sometimes takes 45+ minutes)

---

## Optional: Add More Sales Team Members

**To grant access to other sales reps:**

```powershell
# Individual users
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "salesrep2@broadvoice.com"

# Or grant to entire Azure AD group
$salesGroupId = "<azure-ad-sales-group-id>"
Grant-CsApplicationAccessPolicy `
    -Group $salesGroupId `
    -PolicyName "BV-Provisioning-Transcript-Access"
```

---

## Optional: Better Error Messages (User.Read.All)

**Current:** Error messages show Azure AD GUIDs
**Better:** Error messages show user emails/names

**To enable:**
1. Azure Portal → App Registrations → [Your App] → API Permissions
2. Add a permission → Microsoft Graph → **Application permissions**
3. Search for: `User.Read.All`
4. Select it and click "Add permissions"
5. Click "Grant admin consent for [tenant]"

**Benefit:** Logs will show "adhoz@broadvoice.com" instead of "ca926a60-508f-4c51-9778-cf87b4243784"

**Not required for production** - transcripts will work either way.

---

## Troubleshooting

### PowerShell: "Grant-CsApplicationAccessPolicy: User can't be granted this policy"

**Solution:** User might not be licensed for Teams. Check:
```powershell
Get-CsOnlineUser -Identity "adhoz@broadvoice.com" |
    Select-Object DisplayName, Enabled, TeamsUpgradeEligibility
```

### Test still returns 403 after 30 minutes

**Solution 1: Remove and re-grant policy**
```powershell
# Remove
Grant-CsApplicationAccessPolicy -PolicyName $null -Identity "adhoz@broadvoice.com"

# Wait 5 minutes

# Re-grant
Grant-CsApplicationAccessPolicy -PolicyName "BV-Provisioning-Transcript-Access" -Identity "adhoz@broadvoice.com"
```

**Solution 2: Try Azure AD Object ID instead**
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "ca926a60-508f-4c51-9778-cf87b4243784"
```

### List all users with this policy
```powershell
Get-CsOnlineUser |
    Where-Object {$_.ApplicationAccessPolicy -eq "BV-Provisioning-Transcript-Access"} |
    Select-Object DisplayName, UserPrincipalName, ApplicationAccessPolicy
```

---

## Summary

**Critical Steps:**
1. ✅ Verify permissions are "Application" type in Azure Portal
2. ✅ Create Application Access Policy via PowerShell
3. ✅ Grant policy to adhoz@broadvoice.com
4. ⏱️ Wait 30 minutes
5. 🧪 Run test

**Total time:** ~5 minutes work + 30 minutes wait

---

**Questions?** Contact João Camarate
