# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BroadVoice Service Automation (BVSA) - An agentic workflow system to automate the end-to-end BroadVoice hosted business voice platform service delivery process. The system extracts provisioning data from Salesforce (call transcripts, emails, customer information) and ultimately creates customer accounts via BroadVoice APIs.

## Common Commands

```bash
# Test Salesforce MCP server connection
npx -y @salesforce/mcp --orgs 00DG0000000C8lRMAS --toolsets all

# Future commands to implement:
# python extract_provisioning.py <transcript> <output_csv>  # Extract data from transcripts
# python validate_provisioning.py <csv_file>                # Validate against requirements
# python create_account.py <validated_csv>                  # Create BroadVoice account via API
```

## Architecture & Data Flow

### Pipeline Stages
1. **Data Ingestion** → Salesforce MCP server (transcripts, emails, customer data)
2. **AI Extraction** → 4-pass methodology:
   - Context understanding
   - Direct extraction
   - Logical inference
   - Validation & confidence scoring
3. **Data Validation** → Validate against 80 attributes in broadvoice_attributes_requirements.csv
4. **CSV Generation** → 8-column provisioning format with audit trails
5. **Account Creation** → BroadVoice API integration (future phase)

### Directory Structure
```
provs/                  # Provisioning data and templates
├── broadvoice_attributes_requirements.csv  # Master 80-attribute template
└── *_provisioning.csv                      # Customer-specific provisioning files
```

## Key Data Requirements

The system must extract and validate 80 attributes across 8 categories from broadvoice_attributes_requirements.csv:

### Critical Mandatory Fields
- **User**: First/Last Name, Email, Role (User/Admin), Package (M/P/B), Local Extension
- **Location**: Location Name, Street/City/State/ZIP, E911 Address, Timezone
- **Phone**: Main Number, Device Brand/Model, Number of Devices
- **Configuration**: Network settings, Lines configuration, Call parking settings

### Validation Rules
- Phone numbers: 10 digits, area code verification, N11 detection
- Addresses: E911 compliance, standardization
- Extensions: 3-5 digits, conflict detection
- Devices: Valid models (Polycom/Cisco/Yealink/Obihai)

## Development Workflow

### When processing transcripts:
1. Extract data with confidence scoring (>95% for explicit, >85% for inferred)
2. Validate all mandatory fields before proceeding
3. Track source timestamps for traceability
4. Generate follow-up items for missing critical data

### When implementing new features:
1. Check broadvoice_attributes_requirements.csv for field specifications
2. Maintain CSV output in 8-column schema format
3. Implement validation for all new data extractions
4. Add confidence scoring for AI-based inferences

## Integration Points

### Current
- Salesforce MCP Server - Configured in mcp.json for automated data retrieval
  - Connected to org: 00DG0000000C8lRMAS (jcamarate@broadvoice.com)
  - Provides access to: transcripts, emails, customer data, SOQL queries
  - Uses npx @salesforce/mcp with full toolset enabled

### Pending Implementation
- AI extraction agent using Claude API
- Validation engine for all 80 attributes
- CSV export with completion metrics
- BroadVoice provisioning API integration

## Success Metrics
- Extraction Accuracy: >95% for explicit data
- Inference Accuracy: >85% for deduced data
- Processing Speed: <30 seconds per transcript
- Completeness Rate: >75% fields on first pass
- False Positive Rate: <5%

## Testing Approach

When tests are implemented, focus on:
- Transcript parsing accuracy
- Attribute extraction completeness
- Validation rule enforcement
- Edge cases (multi-site, seasonal implementations)
- E911 compliance verification