# Microsoft Teams Transcript Access - Current Status

## Summary

✅ **Code changes complete** - Per-user access policy support implemented
📋 **Waiting on IT** - Application Access Policy needs to be configured via PowerShell
🧪 **Test ready** - Can verify once policy is active

---

## What We Have

### ✅ Configured

1. **Azure AD Permissions:**
   - ✅ `OnlineMeetings.Read.All` (Application) - Granted
   - ✅ `OnlineMeetingTranscript.Read.All` (Application) - Granted
   - ⚠️ `User.Read.All` (Application) - NOT granted (optional)

2. **Azure Credentials:**
   - ✅ AZURE_CLIENT_ID configured
   - ✅ AZURE_CLIENT_SECRET configured
   - ✅ AZURE_TENANT_ID configured
   - ✅ Authentication successful

3. **Code Updates:**
   - ✅ Enhanced error messages
   - ✅ Organizer email resolution
   - ✅ Access policy pre-checks
   - ✅ Clear PowerShell command guidance

---

## What's Missing

### ❌ Application Access Policy (PowerShell)

**Status:** NOT configured
**Evidence:** Test returns 403 "No application access policy found for this app"

**Required Action:** IT must run PowerShell commands to:
1. Create application access policy
2. Grant policy to meeting organizers (starting with Alejandro)

---

## Test Meeting Details

**Opportunity:** 006Pq00000WKi7LIAT
**Meeting:** Design Call | 37603 | Vcp Lavista Jv Llc-Raleigh Location
**Organizer (Salesforce):** Alejandro De La Hoz (adhoz@broadvoice.com)
**Organizer (Azure AD ID):** `ca926a60-508f-4c51-9778-cf87b4243784`
**Meeting UUID:** `54f446d8-524c-4c32-9e06-48501e299d40`

---

## IT Action Required

### Step 1: Verify Permissions are "Application" Type

**Go to:** Azure Portal → App Registrations → [Your App] → API Permissions

**Check these show Type = "Application":**
- OnlineMeetings.Read.All
- OnlineMeetingTranscript.Read.All

If any show "Delegated", they need to be removed and re-added as **Application** type.

---

### Step 2: Create & Grant Application Access Policy

**Connect to Teams PowerShell:**
```powershell
Install-Module -Name MicrosoftTeams -Force -AllowClobber
Connect-MicrosoftTeams
```

**Get your Azure Client ID:**
- From `.env` file: `AZURE_CLIENT_ID` value
- Or from Azure Portal: App Registrations → Overview → Application (client) ID

**Create the policy:**
```powershell
$appClientId = "<YOUR_AZURE_CLIENT_ID>"

New-CsApplicationAccessPolicy `
    -Identity "BV-Provisioning-Transcript-Access" `
    -AppIds $appClientId `
    -Description "Allows BV provisioning app to access meeting transcripts for sales team"
```

**Grant to Alejandro (choose ONE method):**

**Method A - By Email (recommended):**
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "adhoz@broadvoice.com"
```

**Method B - By Azure AD ID:**
```powershell
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "ca926a60-508f-4c51-9778-cf87b4243784"
```

**Verify it was granted:**
```powershell
Get-CsOnlineUser -Identity "adhoz@broadvoice.com" |
    Select-Object DisplayName, UserPrincipalName, ApplicationAccessPolicy

# Should show:
# ApplicationAccessPolicy : BV-Provisioning-Transcript-Access
```

---

### Step 3: Wait for Propagation

⏱️ **CRITICAL:** Policy changes take **up to 30 minutes** to propagate through Microsoft's systems.

After granting the policy:
- Wait at least 30 minutes
- Then run test (Step 4)

---

### Step 4: Test Configuration

**After waiting 30 minutes, run:**

```bash
cd /Users/jcamarate/dev/bv-service-delivery/agents/bv-provisioning-agent
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
```

**Expected SUCCESS output:**
```
✅ Successfully authenticated with Microsoft Graph
✅ Extracting transcript for organizer: ca926a60-508f-4c51-9778-cf87b4243784
✅ Found meeting: Design Call | 37603...
✅ Found N transcripts for meeting
✅ Downloaded transcript content
💾 Saved transcript to: data/006Pq00000WKi7LIAT/teams_transcript_*.txt
```

**If still FAILS with 403:**
- Double-check policy name in Grant command
- Try granting with both email AND Azure AD ID
- Wait another 15-30 minutes
- Verify permission types are "Application" not "Delegated"

---

## Optional: User.Read.All Permission

**Current:** Error messages show Azure AD GUIDs (e.g., `ca926a60-508f-4c51-9778-cf87b4243784`)
**With User.Read.All:** Error messages show emails (e.g., `adhoz@broadvoice.com`)

**To add:**
1. Azure Portal → App Registrations → API Permissions
2. Add permission → Microsoft Graph → **Application permissions**
3. Search for: `User.Read.All`
4. Grant admin consent

**Impact:** Better logging and error messages only - transcript extraction works either way.

---

## Verification Commands

### Quick verification (check configuration):
```bash
python verify_access.py
```

### Full test (extract actual transcript):
```bash
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
```

---

## Security Model

### What Access Is Granted

✅ **App can access:**
- Meetings **organized by** users in the policy (e.g., adhoz@broadvoice.com)
- Transcripts for those meetings

❌ **App CANNOT access:**
- Meetings organized by other users
- Meetings where authorized user is just a participant (not organizer)
- Any other Teams data

### Example Scenario

**If policy granted to:** adhoz@broadvoice.com

| Meeting | Organizer | App Access |
|---------|-----------|------------|
| Design Call #1 | adhoz@broadvoice.com | ✅ YES |
| Design Call #2 | other-user@broadvoice.com | ❌ NO |
| Design Call #3 | adhoz@broadvoice.com | ✅ YES |

This ensures **least-privilege access** - only specific users' meetings are accessible.

---

## Next Users

**To grant access to additional sales team members:**

```powershell
# Add another user
Grant-CsApplicationAccessPolicy `
    -PolicyName "BV-Provisioning-Transcript-Access" `
    -Identity "salesrep2@broadvoice.com"

# Or add entire sales team group
$salesGroupId = "<azure-ad-group-id>"
Grant-CsApplicationAccessPolicy `
    -Group $salesGroupId `
    -PolicyName "BV-Provisioning-Transcript-Access"
```

---

## Timeline

1. ✅ **Day 1:** Code changes completed
2. ⏳ **Day 1:** IT configures policy (5 minutes)
3. ⏱️ **Day 1:** Wait 30 minutes for propagation
4. 🧪 **Day 1:** Test with opportunity 006Pq00000WKi7LIAT
5. 📈 **Day 2+:** Add more users as needed

**Estimated total time:** 40 minutes from policy creation to working transcripts

---

## Files Created

- `IT_CHECKLIST.md` - Detailed setup instructions for IT
- `verify_access.py` - Automated configuration verification script
- `TEAMS_ACCESS_POLICY_SETUP.md` - Complete setup guide with troubleshooting
- `CURRENT_STATUS.md` - This file

---

## Support

**If test fails after 30 minutes:**
1. Check `IT_CHECKLIST.md` troubleshooting section
2. Re-run `python verify_access.py` for diagnostics
3. Verify policy with `Get-CsOnlineUser` PowerShell command
4. Contact João Camarate with error messages

---

## Ready to Proceed?

Share `IT_CHECKLIST.md` with your IT guy. It has all the commands and step-by-step instructions.

Once policy is configured and 30 minutes have passed, run the test and we'll see the actual transcript extraction!
