"""
Configuration and constants for BV Provisioning Agent
"""
from pathlib import Path

# Salesforce Configuration
SALESFORCE_ORG_USERNAME = "jcamarate@broadvoice.com"
SALESFORCE_ORG_ID = "00DG0000000C8lRMAS"

# Directory Structure
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROVS_DIR = PROJECT_ROOT / "provs"
REQUIREMENTS_CSV = PROJECT_ROOT / "broadvoice_attributes_requirements.csv"

# Extraction Tools
EXTRACTION_SCRIPT = PROJECT_ROOT / "extract_opportunity_data_modular.py"

# Output Format
CSV_DELIMITER = ";"
CSV_COLUMNS = [
    "Category",
    "Attribute",
    "Sub-Attribute",
    "Required/Optional",
    "Extracted Value",
    "Source Timestamp",
    "Status",
    "Notes"
]

# Validation Rules
PHONE_REGEX = r'^\d{10}$'
AREA_CODE_LENGTH = 3
EXTENSION_MIN_LENGTH = 3
EXTENSION_MAX_LENGTH = 5
ZIP_CODE_LENGTH = 5
STATE_CODE_LENGTH = 2

# N11 Extensions (must be reassigned)
N11_CODES = ['211', '311', '411', '511', '611', '711', '811', '911']

# Valid Device Brands
DEVICE_BRANDS = ['Polycom', 'Cisco', 'Yealink', 'Obihai']

# Valid Package Types
PACKAGE_TYPES = ['M', 'P', 'B']  # Metered, Pro, Basic

# Valid Role Types
ROLE_TYPES = ['User', 'Admin']

# Confidence Scoring Thresholds
CONFIDENCE_EXPLICIT = 95  # For directly stated values
CONFIDENCE_INFERRED = 85  # For logically deduced values
CONFIDENCE_LOW = 50       # For uncertain/assumed values

# Status Values
STATUS_COMPLETE = "Complete"
STATUS_PARTIAL = "Partial"
STATUS_MISSING = "Missing"
STATUS_NOT_REQUIRED = "Not Required"
STATUS_CONFLICT = "Conflict"

# Required Categories (from 80-attribute template)
CATEGORIES = [
    "User Details",
    "Location/Address",
    "Phone Numbers",
    "Device Configuration",
    "Phone Buttons",
    "Fax Configuration",
    "Network Settings",
    "Call Features",
    "Business Information",
    "Notifications",
    "SharePoint/Integration"
]

# Critical Mandatory Fields (must be present for provisioning)
CRITICAL_FIELDS = [
    ("User Details", "First Name"),
    ("User Details", "Last Name"),
    ("User Details", "Email"),
    ("User Details", "Role"),
    ("User Details", "Package"),
    ("User Details", "Local Extension"),
    ("Location/Address", "Location Name"),
    ("Location/Address", "Street Address"),
    ("Location/Address", "City"),
    ("Location/Address", "State"),
    ("Location/Address", "ZIP Code"),
    ("Location/Address", "Timezone"),
    ("Phone Numbers", "Main Number"),
    ("Device Configuration", "Device Brand"),
    ("Device Configuration", "Device Model"),
    ("Device Configuration", "Number of Devices"),
    ("Business Information", "Company Name"),
    ("Business Information", "Implementation Date"),
]

# Data Source Priority (highest to lowest)
SOURCE_PRIORITY = [
    "contract",      # Signed contracts, BOF, LOA
    "spreadsheet",   # Excel files with user details
    "transcript",    # Design call transcripts
    "salesforce",    # Salesforce opportunity/account data
    "email",         # Email communications
    "inferred"       # Logically deduced values
]

# Model Configuration
CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 8192
TEMPERATURE = 0.2  # Lower for more deterministic extraction

# Agent Prompts Directory
PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.txt"
EXTRACTION_PROMPT_FILE = PROMPTS_DIR / "extraction.txt"
VALIDATION_PROMPT_FILE = PROMPTS_DIR / "validation.txt"

# Interactive Mode Configuration
INTERACTIVE_MODE_ENABLED = True
WELCOME_MESSAGE = """
🤖 BV PROVISIONING AGENT - Interactive Mode

I can help you with:
• Extract provisioning data from Salesforce opportunities
• Query Salesforce for accounts, opportunities, contacts, documents
• Check status of existing provisioning files
• Answer questions about BroadVoice requirements and validation rules
• Provide guidance on the extraction process and workflows
• Analyze transcripts, documents, and customer data

Type your request or question. Commands: /help, /clear, /exit
"""

INTERACTIVE_PROMPT = "\n💬 You: "
AGENT_PREFIX = "🤖 Agent: "

INTERACTIVE_HELP = """
Available Commands:
  /help           Show this help message
  /clear          Clear conversation history and start fresh
  /exit           Exit interactive mode

Example Requests:
  "Extract provisioning data for opportunity 0065e00000XxxxxxAAA"
  "What opportunities are open for ABC Property Management?"
  "Show me the status of provisioning for opportunity X"
  "What are the critical mandatory fields?"
  "Query all opportunities closed this month"
  "Explain the 4-pass extraction methodology"
"""
