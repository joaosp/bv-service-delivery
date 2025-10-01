# BV Provisioning Agent

An interactive AI assistant built with Claude Agent SDK that helps with BroadVoice provisioning workflows and Salesforce data operations.

## Overview

This agent provides an intelligent, conversational interface for provisioning operations. Use it interactively to query Salesforce, extract provisioning data, check status, and get guidance - or run autonomous extractions for automation workflows.

## Features

- 💬 **Interactive Mode**: Conversational interface for flexible workflows
- 🤖 **Autonomous Extraction**: Fully automated data extraction for scripting/CI/CD
- 📊 **4-Pass Methodology**: Context → Extract → Infer → Validate for maximum accuracy
- 📋 **80-Attribute Coverage**: Complete provisioning template with all required fields
- 🔍 **Salesforce Queries**: Search opportunities, accounts, contacts, run SOQL
- 📈 **Status Checks**: Review existing provisioning files and metrics
- 🎯 **Multi-Source Analysis**: Transcripts, Excel files, PDFs, contracts, emails
- ✅ **Intelligent Validation**: Confidence scoring, conflict detection, cross-referencing
- 📑 **Comprehensive Reporting**: CSV provisioning files + Markdown status reports

## Architecture

```
bv-provisioning-agent/
├── agent.py              # Main agent orchestrator
├── tools.py              # Custom tool definitions
├── config.py             # Configuration & constants
├── prompts/              # System prompts
│   ├── system.txt        # Main agent instructions
│   ├── extraction.txt    # 4-pass methodology
│   └── validation.txt    # 80-attribute requirements
├── requirements.txt      # Dependencies
└── README.md            # This file
```

## Installation

### Quick Setup

1. **Navigate to agent directory:**
```bash
cd agents/bv-provisioning-agent
```

2. **Configure environment variables:**
```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your actual values
# Required: ANTHROPIC_API_KEY
# Optional: SALESFORCE_ORG_USERNAME, SALESFORCE_ORG_ID
nano .env  # or use your preferred editor
```

**Example .env file:**
```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
SALESFORCE_ORG_USERNAME=your-email@broadvoice.com
SALESFORCE_ORG_ID=00DG0000000C8lRMAS
```

3. **Activate the virtual environment:**
```bash
source activate.sh
```

This will:
- Activate the Python virtual environment
- Load environment variables from .env
- Display available commands
- Warn if ANTHROPIC_API_KEY is not set

4. **Alternative: Set API key via environment (if not using .env):**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### Manual Setup

If you need to set up the environment from scratch:

1. **Create virtual environment:**
```bash
cd agents/bv-provisioning-agent
python3 -m venv venv
```

2. **Activate environment:**
```bash
source venv/bin/activate
```

3. **Install dependencies:**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your values
```

### Verify Installation

```bash
python agent.py --help
```

### Optional: Microsoft Teams Integration

To enable Microsoft Teams meeting transcript extraction:

**1. Azure AD App Setup (one-time):**

Follow detailed instructions in the parent project's `TEAMS_SETUP.md` file:
- Create Azure AD app registration
- Configure API permissions: `OnlineMeetingTranscript.Read.All`, `OnlineMeeting.Read.All`
- Create client secret
- Set up application access policy

**2. Add Azure credentials to `.env`:**

```bash
AZURE_CLIENT_ID=your-application-client-id-here
AZURE_CLIENT_SECRET=your-client-secret-value-here
AZURE_TENANT_ID=your-directory-tenant-id-here
```

**3. Install Teams dependencies:**

```bash
pip install -r requirements.txt  # Includes msal, azure-identity, msgraph-core
```

**Note:** Without Azure credentials, Teams transcript extraction will be skipped. Other transcript sources (VoiceCall, MessagingSession, Task descriptions) will still work normally.

### Parent Project Requirements

Ensure the following exist in the parent project:
- `extract_opportunity_data_modular.py` - Salesforce extraction script
- `cleanup_transcript.py` - Transcript cleaning utility
- `broadvoice_attributes_requirements.csv` - 80-attribute template
- `salesforce_extractors/` - Modular extractor package

## Usage

### Interactive Mode (Recommended)

Start a conversational session to explore data and drive workflows naturally:

```bash
python agent.py --interactive
```

**Example Interactive Session:**
```
🤖 BV PROVISIONING AGENT - Interactive Mode

I can help you with:
• Extract provisioning data from Salesforce opportunities
• Query Salesforce for accounts, opportunities, contacts, documents
• Check status of existing provisioning files
• Answer questions about BroadVoice requirements and validation rules
• Provide guidance on the extraction process and workflows

Type your request or question. Commands: /help, /clear, /exit

💬 You: What opportunities are we working on for ABC Property Management?

🤖 Agent: Let me search Salesforce for opportunities related to ABC Property Management...
🔧 Using tool: query_salesforce_general...

I found 3 open opportunities for ABC Property Management:
1. ABC - Main Office Expansion (0065e00000ABC123AAA) - Closes 2025-01-15
2. ABC - Satellite Location (0065e00000ABC456AAA) - Closes 2025-02-01
3. ABC - Additional Users (0065e00000ABC789AAA) - Closes 2025-01-30

Would you like me to extract provisioning data for any of these?

💬 You: Yes, extract data for the Main Office Expansion one

🤖 Agent: I'll extract provisioning requirements for opportunity 0065e00000ABC123AAA - ABC - Main Office Expansion. This will:
1. Pull all Salesforce data (contacts, documents, transcripts)
2. Analyze materials using 4-pass methodology
3. Generate provisioning CSV with 80 attributes
4. Create status report

Starting extraction now...
🔧 Using tool: extract_salesforce_data...
[extraction proceeds]

💬 You: What's missing from the extraction?

🤖 Agent: Let me check the provisioning file...
🔧 Using tool: read_provisioning_file...

The extraction is 78/80 complete (97.5%). Missing attributes:
• Network Settings → Custom Config (Optional)
• Call Features → Conference Bridge (Optional)

Both are optional fields. The extraction has all 18 critical mandatory fields needed for provisioning.

💬 You: /exit

👋 Goodbye!
```

### Autonomous Mode (For Automation)

Run unattended extraction for scripts/CI/CD:

```bash
python agent.py --opp-id 0065e00000XxxxxxAAA --autonomous
```

### Mode Comparison

| Feature | Interactive Mode | Autonomous Mode |
|---------|-----------------|-----------------|
| **Use Case** | Exploration, Q&A, flexible workflows | Scripts, automation, batch processing |
| **Interaction** | Conversational, back-and-forth | Single execution, no interaction |
| **Salesforce Queries** | ✅ Full query capabilities | ❌ Extraction only |
| **Status Checks** | ✅ Check any opportunity | ❌ Target opportunity only |
| **Guidance** | ✅ Ask questions, get help | ❌ Silent execution |
| **Starting Point** | Open-ended | Requires opportunity ID |

### Interactive Mode Commands

- `/help` - Show available commands and examples
- `/clear` - Clear conversation history and start fresh
- `/exit` - Exit interactive mode

### Advanced Usage

**With initial context:**
```bash
python agent.py --interactive --context "ABC Property Management"
```

**With opportunity context:**
```bash
python agent.py --interactive --opp-id 0065e00000XxxxxxAAA
```

**Custom API key:**
```bash
python agent.py --interactive --api-key sk-ant-xxxxx
```

## What the Agent Can Do

### Provisioning Extractions
- Extract complete provisioning data from Salesforce opportunities
- Analyze transcripts, documents, and structured data
- Apply 4-pass methodology for accuracy
- Generate provisioning CSV with all 80 attributes
- Create comprehensive status reports

### Salesforce Queries
- Search for opportunities by name or account
- Find contacts and their roles
- Query accounts and related records
- Execute custom SOQL queries
- Browse documents and attachments

### Status Operations
- Check if provisioning files exist for opportunities
- Review extraction completeness metrics
- View extracted attribute details
- Check last modification timestamps

### Guidance & Help
- Explain the 80-attribute requirements
- Describe validation rules (phone numbers, extensions, addresses)
- Clarify 4-pass extraction methodology
- Answer questions about BroadVoice provisioning

## Extraction Workflow (When Requested)

1. **Phase 1: Data Extraction**
   - Runs `extract_opportunity_data_modular.py` to pull all Salesforce data
   - Downloads documents, transcripts, contacts, relationships
   - Creates organized directory structure in `data/[OPP_ID]/`

2. **Phase 2: Material Analysis**
   - Analyzes call transcripts (design calls, Teams meetings)
   - Processes Excel spreadsheets (user lists, device inventories)
   - Reviews contract documents (BOF, LOA, agreements)
   - Examines email communications
   - Parses Salesforce structured data

3. **Phase 3: 4-Pass Extraction**
   - **Pass 1**: Context understanding - business structure, stakeholders, scope
   - **Pass 2**: Direct extraction - explicitly stated values with sources
   - **Pass 3**: Logical inference - fill gaps using patterns and best practices
   - **Pass 4**: Validation - confidence scoring, conflict detection

4. **Phase 4: Output Generation**
   - Creates `[OPP_ID]_provisioning.csv` with all 80 attributes
   - Generates `[OPP_ID]_status.md` with comprehensive report
   - Saves to `data/[OPP_ID]/provs/` directory

## Output Files

### Provisioning CSV
**Location**: `data/[OPP_ID]/provs/[OPP_ID]_provisioning.csv`

8-column format:
```csv
Category;Attribute;Sub-Attribute;Required/Optional;Extracted Value;Source Timestamp;Status;Notes
```

**Status Values:**
- `Complete` - Value extracted with >85% confidence
- `Partial` - Some sub-attributes present, others missing
- `Missing` - No value found
- `Conflict` - Multiple conflicting values
- `Not Required` - Optional field not applicable

### Status Report
**Location**: `data/[OPP_ID]/provs/[OPP_ID]_status.md`

Includes:
- Executive Summary (completeness %, critical gaps, readiness)
- Data Sources Analyzed (Salesforce, transcripts, documents)
- Provisioning Requirements (complete/partial/missing breakdown)
- Data Quality Metrics (confidence levels, conflicts)
- Next Steps (actions required, customer follow-up)

## Custom Tools

The agent uses 6 custom tools:

1. **extract_salesforce_data** - Comprehensive Salesforce extraction
2. **clean_transcript** - Transcript formatting and cleanup
3. **analyze_documents** - Excel/spreadsheet analysis
4. **validate_attributes** - 80-attribute validation
5. **generate_provisioning_csv** - Final CSV generation
6. **generate_status_report** - Status report creation

## Configuration

Edit `config.py` to customize:

- **Salesforce settings**: Org username, org ID
- **Validation rules**: Phone format, extensions, N11 codes
- **Confidence thresholds**: Explicit (>95%), Inferred (>85%)
- **Device brands**: Polycom, Cisco, Yealink, Obihai
- **Critical fields**: 18 mandatory attributes for provisioning

## 4-Pass Methodology

### Pass 1: Context Understanding
Map customer business structure, stakeholders, scope, and timeline

### Pass 2: Direct Extraction
Capture explicitly stated values with source timestamps:
- `"transcript 05:23-05:45"` - timestamp range
- `"spreadsheet users.xlsx row 15"` - Excel reference
- `"contract BOF_signed.pdf page 3"` - PDF location

### Pass 3: Logical Inference
Fill gaps using:
- Extension patterns (100-199 → next available)
- Industry standards (default business hours)
- User role patterns (all receptionists → same device)

### Pass 4: Validation & Scoring
- Cross-reference across sources
- Assign confidence scores (>95% explicit, >85% inferred)
- Flag conflicts and inconsistencies
- Validate phone numbers, addresses, extensions

## Success Metrics

- **Extraction Accuracy**: >95% for explicit data
- **Inference Accuracy**: >85% for deduced data
- **Completeness Rate**: >75% fields on first pass
- **False Positive Rate**: <5%

## Error Handling

The agent continues gracefully when:
- Salesforce queries fail (documents and continues)
- Transcripts missing (notes in report)
- Documents unreadable (flags for manual review)
- Partial data available (generates outputs anyway)

## Troubleshooting

**Agent fails to start:**
- Check `ANTHROPIC_API_KEY` environment variable
- Verify Python 3.8+ installed
- Install dependencies: `pip install -r requirements.txt`

**Extraction errors:**
- Verify Salesforce CLI authenticated: `sf org list`
- Check opportunity ID format (18 chars, starts with 006)
- Ensure parent scripts exist: `extract_opportunity_data_modular.py`

**Missing data in output:**
- Review status report for data source inventory
- Check if documents were downloaded successfully
- Verify transcripts exist in `data/[OPP_ID]/transcripts/`

## Integration

This agent integrates with:
- **Salesforce MCP Server** - Data extraction (configured in parent `mcp.json`)
- **Salesforce Extractors** - Modular extraction library (`salesforce_extractors/`)
- **Cleanup Scripts** - Transcript processing (`cleanup_transcript.py`)
- **Requirements Template** - 80-attribute validation (`broadvoice_attributes_requirements.csv`)

## Development

**Add new tools:**
1. Define function in `tools.py`
2. Add tool schema to `TOOLS` list
3. Agent will automatically discover and use it

**Modify prompts:**
1. Edit text files in `prompts/` directory
2. Agent reloads prompts on each run

**Adjust validation:**
1. Update `config.py` constants
2. Modify validation logic in `tools.py`

## Future Enhancements

- [ ] Interactive mode for real-time Q&A
- [ ] Batch processing for multiple opportunities
- [ ] Direct BroadVoice API integration
- [ ] Automated follow-up email generation
- [ ] Multi-language support for international deployments

## License

Internal BroadVoice Service Delivery tool - All rights reserved

## Support

For issues or questions:
- Review logs in agent output
- Check `data/[OPP_ID]/summary.md` for extraction details
- Contact Service Delivery team
