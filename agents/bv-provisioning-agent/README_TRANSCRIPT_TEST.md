# Transcript Extraction Test Suite

## Overview

This test suite validates the Salesforce transcript extraction pipeline, including Microsoft Teams integration via Azure Graph API.

## Fixed Issues

### SOQL Semi-Join Error ✅
**Fixed in:** `salesforce_extractors/transcripts.py`

The original query:
```sql
SELECT ... FROM VoiceCall
WHERE Id IN (SELECT CallObject FROM Task WHERE ...)
```

Was causing error: `Entity 'Task' is not supported for semi join inner selects`

**Solution:** Changed to a two-step approach:
1. Query Task records first to get CallObject IDs
2. Query VoiceCall records directly using those IDs

## Test Script

**Location:** `agents/bv-provisioning-agent/test_transcript_extraction.py`

### Features

- ✅ Tests any Salesforce opportunity via `--opp-id` parameter
- ✅ Loads Azure credentials from `.env` file
- ✅ Tests complete extraction pipeline:
  - Opportunity access validation
  - Azure credentials check
  - VoiceCall extraction
  - VideoCall extraction
  - Microsoft Teams transcript extraction
  - End-to-end extraction workflow
- ✅ Generates detailed JSON test report
- ✅ Returns proper exit codes (0 = pass, 1 = fail)

### Usage

```bash
cd agents/bv-provisioning-agent

# Test any opportunity
python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT
python test_transcript_extraction.py --opp-id <any-opportunity-id>

# Use different Salesforce org
python test_transcript_extraction.py --opp-id 006ABC123 --org myorg@company.com

# Specify output directory
python test_transcript_extraction.py --opp-id 006ABC123 --output-dir /tmp/tests
```

### Configuration

The test automatically loads environment variables from `.env` in the same directory.

**Required for Teams Integration:**
```bash
# agents/bv-provisioning-agent/.env
AZURE_CLIENT_ID=your-client-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
AZURE_TENANT_ID=your-tenant-id-here
```

**Note:** Tests will pass even without Azure credentials. Teams transcript extraction is simply skipped if credentials are not configured.

### Test Results

Results are saved to: `data/<opportunity-id>/test_results.json`

Example output:
```json
{
  "test_results": {
    "timestamp": "2025-10-01T18:03:55.911676",
    "tests_passed": 6,
    "tests_failed": 0,
    "test_details": [...]
  },
  "extraction_results": {
    "voice_calls": 0,
    "video_calls": 0,
    "teams_calls": 0,
    "teams_transcripts": 0,
    "complete_extraction": {...}
  }
}
```

## Example Run

```bash
$ python test_transcript_extraction.py --opp-id 006Pq00000WKi7LIAT

✅ Loaded environment variables from: .../agents/bv-provisioning-agent/.env
======================================================================
🧪 TRANSCRIPT EXTRACTION TEST SUITE
======================================================================
Opportunity ID: 006Pq00000WKi7LIAT
Org: jcamarate@broadvoice.com

✅ PASS - Opportunity Access
✅ PASS - Azure Credentials
✅ PASS - VoiceCall Extraction
✅ PASS - VideoCall Extraction
✅ PASS - Teams Transcript Extraction
✅ PASS - Complete Extraction

======================================================================
📊 TEST SUMMARY
======================================================================
Tests Passed: 6
Tests Failed: 0
Total Tests: 6

✅ ALL TESTS PASSED
======================================================================
```

## Testing Different Opportunities

To test with an opportunity that has actual Teams meetings:

1. Find an opportunity with VideoCall records linked
2. Ensure the VideoCall has `VendorName = 'MSTeams'`
3. Configure Azure credentials in `.env`
4. Run: `python test_transcript_extraction.py --opp-id <opp-id-with-teams-calls>`

The test will automatically detect Teams meetings and attempt to extract transcripts via Microsoft Graph API.

## Troubleshooting

### No VoiceCall/VideoCall found
This is normal if the opportunity doesn't have linked call records. The test still passes as the queries execute successfully.

### Azure Authentication Fails
- Verify credentials in `.env` are correct
- Check Azure app has required Graph API permissions:
  - `OnlineMeetings.Read.All`
  - `OnlineMeetingTranscript.Read.All`

### SOQL Errors
If you see SOQL errors, ensure you're using the latest version of `salesforce_extractors/transcripts.py` with the semi-join fix.

## Exit Codes

- `0` - All tests passed
- `1` - One or more tests failed or error occurred
