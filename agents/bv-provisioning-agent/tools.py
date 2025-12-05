"""
Custom tools for BV Provisioning Agent using Claude Agent SDK
"""
import subprocess
import signal
import json
import csv
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
import os

try:
    from claude_agent_sdk import tool
except ImportError:
    # Fallback decorator if SDK not installed
    def tool(name: str, description: str, input_schema: dict):
        def decorator(func):
            func.tool_name = name
            func.tool_description = description
            func.tool_input_schema = input_schema
            return func
        return decorator

from config import (
    PROJECT_ROOT,
    EXTRACTION_SCRIPT,
    REQUIREMENTS_CSV,
    CSV_DELIMITER,
    CSV_COLUMNS,
    SALESFORCE_ORG_USERNAME,
    DATA_DIR,
    BHIVE_MCP_ENABLED,
    BHIVE_MCP_SERVER_URL,
    BHIVE_PROVISIONING_FILE,
    BHIVE_DEFAULT_CONTRACT_DURATION,
    BHIVE_DEFAULT_PAYMENT_TERM,
    BHIVE_AUTO_ACTIVATE_CONTRACT,
    CANCELLATION_ENABLED,
    SALESFORCE_EXTRACTION_TIMEOUT,
    SUBPROCESS_POLL_INTERVAL,
    SUBPROCESS_TERMINATION_GRACE
)
from cancellation import (
    get_cancellation_manager,
    OperationState,
    CancellationRequestedError
)


def _truncate_text(text: str, max_size: int = 50000, truncation_msg: str = "[OUTPUT TRUNCATED]") -> tuple:
    """
    Truncate text if it exceeds max_size

    Args:
        text: Text to truncate
        max_size: Maximum size in characters
        truncation_msg: Message to append when truncated

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if not text:
        return text, False

    if len(text) <= max_size:
        return text, False

    truncated = text[:max_size] + f"\n\n... {truncation_msg} ...\n(Showing first {max_size} of {len(text)} characters)"
    return truncated, True


def _format_tool_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format tool response for Claude Agent SDK

    Args:
        data: Dictionary with tool execution results

    Returns:
        Formatted response with content blocks
    """
    # Convert the data dict to a JSON string for the text content
    text_content = json.dumps(data, indent=2)

    return {
        "content": [{
            "type": "text",
            "text": text_content
        }],
        "is_error": not data.get("success", False)
    }


@tool(
    "extract_salesforce_data",
    "Extract comprehensive Salesforce data for an opportunity including contacts, documents, transcripts, and relationships",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID (18 characters starting with 006)"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def extract_salesforce_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract comprehensive Salesforce data for an opportunity.

    Supports cancellation via the CancellationManager. If cancelled, preserves
    any data that was already downloaded.

    Args:
        args: Dictionary with 'opportunity_id' key

    Returns:
        Formatted response with extraction results and file paths
    """
    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    # Get cancellation manager and set state
    cancellation_mgr = get_cancellation_manager()
    cancellation_mgr.set_state(OperationState.EXTRACTING_SALESFORCE)
    cancellation_mgr.set_opportunity_id(opp_id)

    process = None
    try:
        # Run the modular extraction script using Popen for cancellation support
        cmd = [
            'python3',
            str(EXTRACTION_SCRIPT),
            '--opp-id', opp_id,
            '--output-dir', str(DATA_DIR)
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT
        )

        # Poll for completion with cancellation checks
        start_time = datetime.now()
        stdout_data = ""
        stderr_data = ""

        while process.poll() is None:
            # Check for cancellation
            if CANCELLATION_ENABLED and cancellation_mgr.is_cancelled():
                print(f"[Tool:extract_salesforce_data] Cancellation detected, terminating subprocess...")

                # Graceful termination
                process.terminate()

                # Wait for grace period
                try:
                    process.wait(timeout=SUBPROCESS_TERMINATION_GRACE)
                except subprocess.TimeoutExpired:
                    # Force kill if still running
                    print(f"[Tool:extract_salesforce_data] Process did not terminate, sending SIGKILL...")
                    process.kill()
                    process.wait()

                # Determine output directory for partial data
                data_dir = DATA_DIR / opp_id

                return _format_tool_response({
                    "success": False,
                    "cancelled": True,
                    "opportunity_id": opp_id,
                    "data_preserved": True,
                    "partial_output_directory": str(data_dir) if data_dir.exists() else None,
                    "message": "Salesforce extraction cancelled. Any downloaded data has been preserved."
                })

            # Check for timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > SALESFORCE_EXTRACTION_TIMEOUT:
                print(f"[Tool:extract_salesforce_data] Timeout after {elapsed:.1f}s, terminating...")
                process.terminate()
                try:
                    process.wait(timeout=SUBPROCESS_TERMINATION_GRACE)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

                return _format_tool_response({
                    "success": False,
                    "error": f"Extraction timed out after {SALESFORCE_EXTRACTION_TIMEOUT} seconds",
                    "opportunity_id": opp_id
                })

            # Sleep before next check
            await asyncio.sleep(SUBPROCESS_POLL_INTERVAL)

        # Process completed - read output
        stdout_data, stderr_data = process.communicate()

        if process.returncode != 0:
            return _format_tool_response({
                "success": False,
                "error": stderr_data,
                "output": stdout_data
            })

        # Determine output directory (agent's data directory)
        data_dir = DATA_DIR / opp_id

        # Truncate stdout to prevent buffer overflow
        truncated_stdout, was_truncated = _truncate_text(stdout_data, max_size=50000)

        response_data = {
            "success": True,
            "opportunity_id": opp_id,
            "output_directory": str(data_dir),
            "extraction_output": truncated_stdout,
            "files_created": {
                "opportunity": str(data_dir / "opportunity.json"),
                "contacts": str(data_dir / "contacts.json"),
                "documents": str(data_dir / "documents.json"),
                "transcripts": str(data_dir / "transcripts.json"),
                "relationships": str(data_dir / "relationships.json"),
                "summary": str(data_dir / "summary.md"),
                "complete_data": str(data_dir / "complete_data.json")
            }
        }

        if was_truncated:
            response_data["warning"] = "Extraction output was truncated due to size. Full output saved to files."

        return _format_tool_response(response_data)

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })
    finally:
        # Reset state when done
        cancellation_mgr.set_state(OperationState.IDLE)

        # Ensure process is cleaned up
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


@tool(
    "analyze_documents",
    "Analyze Excel/spreadsheet documents to extract user lists, device inventories, and other structured data",
    {
        "type": "object",
        "properties": {
            "documents_directory": {
                "type": "string",
                "description": "Path to the documents directory containing spreadsheets"
            }
        },
        "required": ["documents_directory"]
    }
)
async def analyze_documents(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze Excel/spreadsheet documents for user data

    Args:
        args: Dictionary with 'documents_directory' key

    Returns:
        Formatted response with analysis results
    """
    docs_dir = Path(args.get('documents_directory', ''))

    # LOGGING: Entry point
    print(f"[Tool:analyze_documents] Called with directory: {docs_dir}")

    if not docs_dir.exists():
        print(f"[Tool:analyze_documents] ❌ Directory not found: {docs_dir}")
        return _format_tool_response({
            "success": False,
            "error": f"Directory not found: {docs_dir}"
        })

    try:
        spreadsheets_dir = docs_dir / 'spreadsheets'
        results = {
            "success": True,
            "files_analyzed": [],
            "data_extracted": {}
        }

        if not spreadsheets_dir.exists():
            print(f"[Tool:analyze_documents] No spreadsheets directory found at {spreadsheets_dir}")
            return _format_tool_response({
                "success": True,
                "files_analyzed": [],
                "message": "No spreadsheets directory found"
            })

        # Find all Excel files
        excel_files = list(spreadsheets_dir.glob('*.xlsx')) + list(spreadsheets_dir.glob('*.xls'))
        print(f"[Tool:analyze_documents] Found {len(excel_files)} Excel file(s) in {spreadsheets_dir}")

        for excel_file in excel_files:
            print(f"[Tool:analyze_documents] Analyzing: {excel_file.name}")
            try:
                # Read Excel file
                df = pd.read_excel(excel_file, sheet_name=None)  # Read all sheets

                file_data = {
                    "file_path": str(excel_file),
                    "sheets": {}
                }

                total_rows = 0
                for sheet_name, sheet_df in df.items():
                    # Convert to dictionary for easier processing
                    sheet_data = sheet_df.to_dict('records')
                    row_count = len(sheet_data)
                    total_rows += row_count

                    file_data["sheets"][sheet_name] = {
                        "row_count": row_count,
                        "columns": list(sheet_df.columns),
                        "sample_data": sheet_data[:5] if sheet_data else []  # First 5 rows as sample
                    }

                    print(f"[Tool:analyze_documents]   Sheet '{sheet_name}': {row_count} rows, {len(sheet_df.columns)} columns")
                    print(f"[Tool:analyze_documents]     Columns: {', '.join(list(sheet_df.columns)[:5])}{'...' if len(sheet_df.columns) > 5 else ''}")

                print(f"[Tool:analyze_documents] ✅ Successfully analyzed {excel_file.name} ({len(df)} sheets, {total_rows} total rows)")
                results["files_analyzed"].append(excel_file.name)
                results["data_extracted"][excel_file.name] = file_data

            except Exception as e:
                print(f"[Tool:analyze_documents] ❌ Error analyzing {excel_file.name}: {str(e)}")
                results["files_analyzed"].append(f"{excel_file.name} (ERROR: {str(e)})")

        # LOGGING: Summary
        print(f"[Tool:analyze_documents] ═══════════════════════════════════════")
        print(f"[Tool:analyze_documents] Document Analysis Complete")
        print(f"[Tool:analyze_documents] Total files analyzed: {len(results['files_analyzed'])}")
        print(f"[Tool:analyze_documents] Successful extractions: {len(results['data_extracted'])}")
        print(f"[Tool:analyze_documents] ═══════════════════════════════════════")

        return _format_tool_response(results)

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "validate_attributes",
    "Validate extracted attributes against the 80-attribute requirements template",
    {
        "type": "object",
        "properties": {
            "attributes_data": {
                "type": "object",
                "description": "Dictionary of extracted attributes with their values, sources, and statuses"
            }
        },
        "required": ["attributes_data"]
    }
)
async def validate_attributes(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate extracted attributes against the 80-attribute requirements

    Args:
        args: Dictionary with 'attributes_data' containing extracted provisioning data

    Returns:
        Formatted response with validation results
    """
    attributes_data = args.get('attributes_data', {})

    # LOGGING: Entry point
    print(f"[Tool:validate_attributes] Called with {len(attributes_data)} extracted attributes")

    try:
        # Load requirements template
        requirements = []
        with open(REQUIREMENTS_CSV, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            requirements = list(reader)

        print(f"[Tool:validate_attributes] Loaded {len(requirements)} attribute requirements from template")

        validation_results = {
            "success": True,
            "total_attributes": len(requirements),
            "validated": 0,
            "complete": 0,
            "partial": 0,
            "missing": 0,
            "conflicts": 0,
            "critical_missing": [],
            "details": []
        }

        for req in requirements:
            category = req['Category']
            attribute = req['Attribute']
            required = req['Required/Optional']

            # Check if attribute exists in extracted data
            attr_key = f"{category}|{attribute}"
            extracted_value = attributes_data.get(attr_key, {})

            validation_results["validated"] += 1

            status = extracted_value.get('status', 'Missing')

            if status == 'Complete':
                validation_results["complete"] += 1
            elif status == 'Partial':
                validation_results["partial"] += 1
            elif status == 'Conflict':
                validation_results["conflicts"] += 1
            else:
                validation_results["missing"] += 1

                # Check if it's a critical mandatory field
                if required == 'Mandatory':
                    validation_results["critical_missing"].append({
                        "category": category,
                        "attribute": attribute
                    })

            validation_results["details"].append({
                "category": category,
                "attribute": attribute,
                "required": required,
                "status": status,
                "value": extracted_value.get('value', ''),
                "source": extracted_value.get('source', '')
            })

        # Calculate completeness percentage
        validation_results["completeness_percentage"] = round(
            (validation_results["complete"] / validation_results["total_attributes"]) * 100, 1
        )

        # LOGGING: Summary
        print(f"[Tool:validate_attributes] ═══════════════════════════════════════")
        print(f"[Tool:validate_attributes] Validation Complete")
        print(f"[Tool:validate_attributes] ═══════════════════════════════════════")
        print(f"[Tool:validate_attributes] Total attributes: {validation_results['total_attributes']}")
        print(f"[Tool:validate_attributes] Complete: {validation_results['complete']} ({validation_results['completeness_percentage']}%)")
        print(f"[Tool:validate_attributes] Partial: {validation_results['partial']}")
        print(f"[Tool:validate_attributes] Missing: {validation_results['missing']}")
        print(f"[Tool:validate_attributes] Conflicts: {validation_results['conflicts']}")
        print(f"[Tool:validate_attributes] Critical mandatory missing: {len(validation_results['critical_missing'])}")

        if validation_results["critical_missing"]:
            print(f"[Tool:validate_attributes] ❌ Critical MANDATORY fields missing (first 10):")
            for item in validation_results["critical_missing"][:10]:
                print(f"[Tool:validate_attributes]   - {item['category']}|{item['attribute']}")
            if len(validation_results["critical_missing"]) > 10:
                print(f"[Tool:validate_attributes]   ... and {len(validation_results['critical_missing']) - 10} more")

        print(f"[Tool:validate_attributes] ═══════════════════════════════════════")

        return _format_tool_response(validation_results)

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "generate_provisioning_csv",
    "Generate the final provisioning CSV file with all 80 attributes",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            },
            "attributes_data": {
                "type": "object",
                "description": "Dictionary of extracted attributes with their values, sources, and statuses"
            }
        },
        "required": ["opportunity_id", "attributes_data"]
    }
)
async def generate_provisioning_csv(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate final provisioning CSV file with all 80 attributes

    Args:
        args: Dictionary with 'opportunity_id' and 'attributes_data'

    Returns:
        Formatted response with file generation results
    """
    opp_id = args.get('opportunity_id', '')
    attributes_data = args.get('attributes_data', {})

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    # LOGGING: Entry point
    print(f"[Tool:generate_provisioning_csv] Called for opportunity: {opp_id}")
    print(f"[Tool:generate_provisioning_csv] Received attributes_data with {len(attributes_data)} keys")

    if len(attributes_data) > 0:
        print(f"[Tool:generate_provisioning_csv] Sample attribute keys (first 5):")
        for i, key in enumerate(list(attributes_data.keys())[:5]):
            value_preview = str(attributes_data[key].get('value', ''))[:50]
            status = attributes_data[key].get('status', 'Unknown')
            print(f"[Tool:generate_provisioning_csv]   {i+1}. {key} = '{value_preview}' (status: {status})")
    else:
        print(f"[Tool:generate_provisioning_csv] ⚠️  WARNING: attributes_data is EMPTY - all fields will be 'Missing'")

    try:
        # Create provs directory in agent's data directory
        provs_dir = DATA_DIR / opp_id / 'provs'
        provs_dir.mkdir(parents=True, exist_ok=True)

        csv_file = provs_dir / f"{opp_id}_provisioning.csv"

        # Load requirements template to ensure all 80 attributes
        requirements = []
        with open(REQUIREMENTS_CSV, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            requirements = list(reader)

        print(f"[Tool:generate_provisioning_csv] Loaded {len(requirements)} attribute requirements from template")

        # ═══════════════════════════════════════════════════════════
        # KEY NORMALIZATION: Handle format variations
        # ═══════════════════════════════════════════════════════════

        # Build a mapping from potential snake_case keys to template format
        def to_snake_case(text):
            """Convert 'First Name' to 'first_name'"""
            import re
            # Remove special chars, convert to lowercase, replace spaces with underscores
            text = re.sub(r'[^\w\s]', '', text.lower())
            text = re.sub(r'\s+', '_', text)
            return text

        # Auto-generate potential key variations
        snake_to_template = {}
        for req in requirements:
            category = req['Category']
            attribute = req['Attribute']
            sub_attribute = req.get('Sub-Attribute', '')

            # Template format key
            template_key = f"{category}|{attribute}"
            if sub_attribute:
                template_key = f"{category}|{attribute}|{sub_attribute}"

            # Potential snake_case variations
            category_snake = to_snake_case(category)
            attr_snake = to_snake_case(attribute)

            # Common patterns agents might use
            variations = [
                f"{category_snake}_{attr_snake}",  # user_details_first_name
                f"{attr_snake}",  # first_name (category omitted)
                f"user_{attr_snake}" if "user" in category.lower() else f"{category_snake}_{attr_snake}",
                f"location_{attr_snake}" if "location" in category.lower() or "address" in category.lower() else None,
                f"phone_{attr_snake}" if "phone" in category.lower() else None,
                f"device_{attr_snake}" if "device" in category.lower() else None,
            ]

            for variant in variations:
                if variant:
                    snake_to_template[variant] = template_key

            # For sub-attributes, try with sub-attribute suffix
            if sub_attribute:
                sub_snake = to_snake_case(sub_attribute)
                snake_to_template[f"{attr_snake}_{sub_snake}"] = template_key
                snake_to_template[f"{category_snake}_{attr_snake}_{sub_snake}"] = template_key

        # Analyze the format of incoming keys
        template_format_count = sum(1 for k in attributes_data.keys() if '|' in k)
        other_format_count = len(attributes_data) - template_format_count

        print(f"[Tool:generate_provisioning_csv] ─────────────────────────────────────")
        print(f"[Tool:generate_provisioning_csv] Format Analysis:")
        print(f"[Tool:generate_provisioning_csv]   Keys in template format (Category|Attribute): {template_format_count}")
        print(f"[Tool:generate_provisioning_csv]   Keys in other format: {other_format_count}")

        # Create a smart lookup function
        def get_extracted_value(template_key):
            """Try to find value using template key or alternative formats"""
            # Try direct template format first
            if template_key in attributes_data:
                return attributes_data[template_key]

            # Try to find a match using our snake_case mapping
            for snake_key, mapped_template_key in snake_to_template.items():
                if mapped_template_key == template_key and snake_key in attributes_data:
                    return attributes_data[snake_key]

            # No match found
            return {}

        # Sample the mappings being applied
        if other_format_count > 0:
            sample_mappings = []
            for snake_key in list(attributes_data.keys())[:5]:
                if '|' not in snake_key:  # Not template format
                    mapped = snake_to_template.get(snake_key)
                    if mapped:
                        sample_mappings.append(f"{snake_key} → {mapped}")

            if sample_mappings:
                print(f"[Tool:generate_provisioning_csv]   Applying normalization (sample mappings):")
                for mapping in sample_mappings:
                    print(f"[Tool:generate_provisioning_csv]     {mapping}")

        print(f"[Tool:generate_provisioning_csv] ─────────────────────────────────────")

        # Track statistics
        stats = {
            'total': 0,
            'populated': 0,
            'missing': 0,
            'inferred': 0,
            'mandatory_missing': [],
            'populated_attributes': [],
            'normalized_count': 0  # Track how many used normalization
        }

        # Write provisioning CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=CSV_DELIMITER)
            writer.writeheader()

            for req in requirements:
                category = req['Category']
                attribute = req['Attribute']
                sub_attribute = req.get('Sub-Attribute', '')
                required = req['Required/Optional']

                # Get extracted data using smart lookup
                attr_key = f"{category}|{attribute}"
                if sub_attribute:
                    attr_key = f"{category}|{attribute}|{sub_attribute}"

                extracted = get_extracted_value(attr_key)  # ← Use smart lookup

                # Track if normalization was used
                if extracted and attr_key not in attributes_data:
                    stats['normalized_count'] += 1

                value = extracted.get('value', '')
                status = extracted.get('status', 'Missing')

                row = {
                    'Category': category,
                    'Attribute': attribute,
                    'Sub-Attribute': sub_attribute,
                    'Required/Optional': required,
                    'Extracted Value': value,
                    'Source Timestamp': extracted.get('source', ''),
                    'Status': status,
                    'Notes': extracted.get('notes', '')
                }

                writer.writerow(row)

                # Update stats
                stats['total'] += 1
                if value and status != 'Missing':
                    stats['populated'] += 1
                    stats['populated_attributes'].append(f"{category}|{attribute}")
                    if 'Inferred' in status:
                        stats['inferred'] += 1
                else:
                    stats['missing'] += 1
                    if 'Mandatory' in required:
                        stats['mandatory_missing'].append(f"{category}|{attribute}")

        # LOGGING: Final stats
        print(f"[Tool:generate_provisioning_csv] ═══════════════════════════════════════")
        print(f"[Tool:generate_provisioning_csv] CSV Generation Complete")
        print(f"[Tool:generate_provisioning_csv] ═══════════════════════════════════════")
        print(f"[Tool:generate_provisioning_csv] Total attributes: {stats['total']}")
        print(f"[Tool:generate_provisioning_csv] Populated: {stats['populated']} ({stats['populated']/stats['total']*100:.1f}%)")
        print(f"[Tool:generate_provisioning_csv] Missing: {stats['missing']} ({stats['missing']/stats['total']*100:.1f}%)")
        print(f"[Tool:generate_provisioning_csv] Inferred: {stats['inferred']}")
        if stats['normalized_count'] > 0:
            print(f"[Tool:generate_provisioning_csv] Normalized (key mapping applied): {stats['normalized_count']}")
        print(f"[Tool:generate_provisioning_csv] ═══════════════════════════════════════")

        if stats['populated'] > 0:
            print(f"[Tool:generate_provisioning_csv] ✅ Populated attributes (first 10):")
            for attr in stats['populated_attributes'][:10]:
                print(f"[Tool:generate_provisioning_csv]   - {attr}")
            if len(stats['populated_attributes']) > 10:
                print(f"[Tool:generate_provisioning_csv]   ... and {len(stats['populated_attributes']) - 10} more")

        if len(stats['mandatory_missing']) > 0:
            print(f"[Tool:generate_provisioning_csv] ❌ Critical MANDATORY attributes still missing ({len(stats['mandatory_missing'])}):")
            for attr in stats['mandatory_missing'][:10]:
                print(f"[Tool:generate_provisioning_csv]   - {attr}")
            if len(stats['mandatory_missing']) > 10:
                print(f"[Tool:generate_provisioning_csv]   ... and {len(stats['mandatory_missing']) - 10} more")

        print(f"[Tool:generate_provisioning_csv] File written to: {csv_file}")
        print(f"[Tool:generate_provisioning_csv] ═══════════════════════════════════════")

        return _format_tool_response({
            "success": True,
            "csv_file": str(csv_file),
            "rows_written": len(requirements),
            "stats": stats,
            "message": f"Provisioning CSV created: {stats['populated']}/{stats['total']} attributes populated"
        })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "generate_status_report",
    "Generate comprehensive status report in Markdown format",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            },
            "opportunity_name": {
                "type": "string",
                "description": "The opportunity name/customer name"
            },
            "validation_results": {
                "type": "object",
                "description": "Results from attribute validation"
            },
            "data_sources": {
                "type": "object",
                "description": "Information about data sources analyzed"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def generate_status_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate comprehensive status report in Markdown format

    Args:
        args: Dictionary with 'opportunity_id', 'validation_results', 'data_sources'

    Returns:
        Formatted response with report generation results
    """
    opp_id = args.get('opportunity_id', '')
    validation_results = args.get('validation_results', {})
    data_sources = args.get('data_sources', {})
    opportunity_name = args.get('opportunity_name', 'Unknown')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    try:
        # Create provs directory in agent's data directory
        provs_dir = DATA_DIR / opp_id / 'provs'
        provs_dir.mkdir(parents=True, exist_ok=True)

        report_file = provs_dir / f"{opp_id}_status.md"

        # Generate report content
        report_lines = [
            f"# BroadVoice Provisioning Status: {opportunity_name}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Opportunity: {opportunity_name} ({opp_id})",
            "",
            "## Executive Summary",
            f"- **Overall Completeness**: {validation_results.get('completeness_percentage', 0)}% ({validation_results.get('complete', 0)} of {validation_results.get('total_attributes', 80)} attributes)",
            f"- **Critical Missing Items**: {len(validation_results.get('critical_missing', []))}",
            f"- **Confidence Level**: {'High' if validation_results.get('completeness_percentage', 0) > 85 else 'Medium' if validation_results.get('completeness_percentage', 0) > 70 else 'Low'}",
            f"- **Ready for Implementation**: {'Yes' if len(validation_results.get('critical_missing', [])) == 0 else 'No'}",
            "",
            "## Data Sources Analyzed",
            "### Salesforce Records",
            f"- Opportunity: {data_sources.get('opportunity', 'N/A')}",
            f"- Contacts: {data_sources.get('contacts_count', 0)} contacts found",
            f"- Documents: {data_sources.get('documents_count', 0)} documents analyzed",
            "",
            "### Transcripts",
            f"- Files processed: {data_sources.get('transcripts_count', 0)}",
            "",
            "## Provisioning Requirements",
            "",
            f"### ✅ Complete ({validation_results.get('complete', 0)} items)",
            "Attributes successfully extracted with high confidence",
            "",
            f"### ⚠️ Partial ({validation_results.get('partial', 0)} items)",
            "Attributes with some missing sub-components",
            "",
            f"### ❌ Missing Critical ({len(validation_results.get('critical_missing', []))} items)"
        ]

        # Add critical missing items
        for item in validation_results.get('critical_missing', []):
            report_lines.append(f"- {item['category']} → {item['attribute']}")

        report_lines.extend([
            "",
            "## Data Quality Metrics",
            f"- Explicit Data Points: {validation_results.get('complete', 0)} (>95% confidence)",
            f"- Inferred Data Points: {validation_results.get('partial', 0)} (85-95% confidence)",
            f"- Conflicting Information: {validation_results.get('conflicts', 0)} items",
            "",
            "## Next Steps",
            "1. **Immediate Actions Required:**",
        ])

        if validation_results.get('critical_missing'):
            report_lines.append("   - Collect missing critical attributes listed above")
        else:
            report_lines.append("   - Review partial attributes for completeness")

        report_lines.extend([
            "",
            "2. **Customer Follow-up Needed:**",
            "   - Verify all extracted information",
            "   - Clarify any conflicting data points",
            "",
            "3. **Implementation Readiness:**",
            f"   - Current completion: {validation_results.get('completeness_percentage', 0)}%",
            f"   - Target: >90% for implementation",
            "",
            "## Notes and Observations",
            "Review the provisioning CSV file for detailed attribute-level information and sources."
        ])

        # Write report
        with open(report_file, 'w') as f:
            f.write('\n'.join(report_lines))

        return _format_tool_response({
            "success": True,
            "report_file": str(report_file),
            "message": f"Status report created successfully: {report_file}"
        })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "query_salesforce_general",
    "Execute general Salesforce queries using sf CLI - search opportunities, accounts, contacts by name or run SOQL queries",
    {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "description": "Type of query: 'search' for text search or 'soql' for SOQL query"
            },
            "query": {
                "type": "string",
                "description": "Search term (for search) or SOQL query string (for soql)"
            },
            "object_type": {
                "type": "string",
                "description": "Salesforce object type (e.g., Opportunity, Account, Contact) - only used for search"
            }
        },
        "required": ["query"]
    }
)
async def query_salesforce_general(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute general Salesforce queries using sf CLI

    Args:
        args: Dictionary with 'query_type', 'query', and optional 'object_type'

    Returns:
        Formatted response with query results
    """
    query_type = args.get('query_type', 'search')
    query = args.get('query', '')
    object_type = args.get('object_type', 'Opportunity')

    if not query:
        return _format_tool_response({
            "success": False,
            "error": "No query provided"
        })

    try:
        if query_type == "soql":
            # Execute SOQL query
            cmd = [
                'sf', 'data', 'query',
                '--query', query,
                '--target-org', SALESFORCE_ORG_USERNAME,
                '--json'
            ]
        else:
            # Text search
            cmd = [
                'sf', 'data', 'query',
                '--query', f"SELECT Id, Name FROM {object_type} WHERE Name LIKE '%{query}%' LIMIT 10",
                '--target-org', SALESFORCE_ORG_USERNAME,
                '--json'
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT
        )

        if result.returncode != 0:
            return _format_tool_response({
                "success": False,
                "error": result.stderr,
                "output": result.stdout
            })

        # Parse JSON response
        try:
            response_data = json.loads(result.stdout)
            records = response_data.get('result', {}).get('records', [])

            return _format_tool_response({
                "success": True,
                "query_type": query_type,
                "query": query,
                "record_count": len(records),
                "records": records
            })
        except json.JSONDecodeError:
            return _format_tool_response({
                "success": True,
                "output": result.stdout
            })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "check_extraction_status",
    "Check if provisioning files exist for an opportunity and return status metrics",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def check_extraction_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if provisioning files exist for an opportunity

    Args:
        args: Dictionary with 'opportunity_id'

    Returns:
        Formatted response with status information
    """
    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    try:
        # Check for data directory
        data_dir = DATA_DIR / opp_id
        provs_dir = data_dir / 'provs'

        if not data_dir.exists():
            return _format_tool_response({
                "success": True,
                "exists": False,
                "message": f"No extraction found for opportunity {opp_id}"
            })

        # Check for provisioning files
        csv_file = provs_dir / f"{opp_id}_provisioning.csv"
        status_file = provs_dir / f"{opp_id}_status.md"

        status_info = {
            "success": True,
            "exists": True,
            "opportunity_id": opp_id,
            "data_directory": str(data_dir),
            "files": {
                "provisioning_csv": csv_file.exists(),
                "status_report": status_file.exists()
            }
        }

        # If CSV exists, parse for metrics
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file, delimiter=CSV_DELIMITER)
                status_counts = df['Status'].value_counts().to_dict()

                status_info["metrics"] = {
                    "total_attributes": len(df),
                    "status_breakdown": status_counts,
                    "completeness_percentage": round(
                        (status_counts.get('Complete', 0) / len(df)) * 100, 1
                    ) if len(df) > 0 else 0,
                    "last_modified": datetime.fromtimestamp(
                        csv_file.stat().st_mtime
                    ).strftime('%Y-%m-%d %H:%M:%S')
                }
            except Exception as e:
                status_info["parse_error"] = str(e)

        # Check for other extracted files
        status_info["extracted_files"] = {
            "opportunity_json": (data_dir / "opportunity.json").exists(),
            "contacts": (data_dir / "contacts.json").exists(),
            "documents": (data_dir / "documents").exists(),
            "transcripts": (data_dir / "transcripts").exists()
        }

        return _format_tool_response(status_info)

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "read_provisioning_file",
    "Read and parse an existing provisioning CSV file to show extracted attributes",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def read_provisioning_file(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read and parse existing provisioning CSV file

    Args:
        args: Dictionary with 'opportunity_id'

    Returns:
        Formatted response with parsed provisioning data
    """
    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    try:
        csv_file = DATA_DIR / opp_id / 'provs' / f"{opp_id}_provisioning.csv"

        if not csv_file.exists():
            return _format_tool_response({
                "success": False,
                "error": f"Provisioning file not found: {csv_file}"
            })

        # Read CSV
        df = pd.read_csv(csv_file, delimiter=CSV_DELIMITER)

        # Organize by category
        by_category = {}
        for _, row in df.iterrows():
            category = row['Category']
            if category not in by_category:
                by_category[category] = []

            by_category[category].append({
                "attribute": row['Attribute'],
                "sub_attribute": row.get('Sub-Attribute', ''),
                "required": row['Required/Optional'],
                "value": row.get('Extracted Value', ''),
                "source": row.get('Source Timestamp', ''),
                "status": row['Status'],
                "notes": row.get('Notes', '')
            })

        # Calculate summary
        status_counts = df['Status'].value_counts().to_dict()

        return _format_tool_response({
            "success": True,
            "opportunity_id": opp_id,
            "file_path": str(csv_file),
            "summary": {
                "total_attributes": len(df),
                "status_breakdown": status_counts,
                "completeness_percentage": round(
                    (status_counts.get('Complete', 0) / len(df)) * 100, 1
                ) if len(df) > 0 else 0
            },
            "data_by_category": by_category
        })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "queue_file_for_teams",
    "Queue a generated file to be sent to the user in MS Teams. Call this immediately after creating CSV files, status reports, or other deliverables that the user needs.",
    {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to send to the user"
            },
            "description": {
                "type": "string",
                "description": "User-friendly description of the file (e.g., 'Provisioning CSV with 80 attributes', 'Status Report')"
            },
            "priority": {
                "type": "string",
                "enum": ["high", "normal", "low"],
                "description": "Priority for sending (high priority files sent first). Use 'high' for critical deliverables like provisioning CSVs and status reports."
            }
        },
        "required": ["file_path"]
    }
)
async def queue_file_for_teams(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Queue file for Teams delivery

    Args:
        args: Dictionary with 'file_path', 'description', 'priority'

    Returns:
        Success confirmation
    """
    from file_queue import file_queue
    from teams_handler import get_current_conversation_id

    file_path = args.get('file_path', '')
    description = args.get('description', '')
    priority = args.get('priority', 'normal')

    # Validate file exists
    if not Path(file_path).exists():
        return _format_tool_response({
            "success": False,
            "error": f"File not found: {file_path}"
        })

    # Get conversation ID from context
    conversation_id = get_current_conversation_id()

    if not conversation_id:
        return _format_tool_response({
            "success": False,
            "error": "No active conversation context. This tool must be called during a Teams conversation."
        })

    # Add to queue
    file_queue.add_file(
        conversation_id=conversation_id,
        file_path=file_path,
        description=description or Path(file_path).name,
        priority=priority
    )

    return _format_tool_response({
        "success": True,
        "message": f"File queued for Teams delivery: {Path(file_path).name}",
        "file_name": Path(file_path).name,
        "description": description or Path(file_path).name,
        "priority": priority
    })


# ═══════════════════════════════════════════════════════════════════════════════
# B-hive Provisioning Tools
# ═══════════════════════════════════════════════════════════════════════════════

@tool(
    "save_bhive_provisioning_data",
    "Save b-hive provisioning data to JSON file. Agent populates this with extracted Salesforce data for b-hive account creation.",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            },
            "opportunity_name": {
                "type": "string",
                "description": "The opportunity/customer name"
            },
            "account": {
                "type": "object",
                "description": "Account details for b-hive",
                "properties": {
                    "name": {"type": "string", "description": "Company name"},
                    "domain": {"type": "string", "description": "Unique SIP domain (lowercase, hyphens allowed)"},
                    "time_zone": {"type": "string", "description": "IANA timezone (e.g., America/New_York)"},
                    "sales_channel_type": {"type": "string", "description": "direct_sales or channel_sales"}
                },
                "required": ["name", "domain", "time_zone"]
            },
            "locations": {
                "type": "array",
                "description": "Array of location objects",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {
                            "type": "object",
                            "properties": {
                                "address": {"type": "string"},
                                "city": {"type": "string"},
                                "state": {"type": "string"},
                                "zip": {"type": "string"}
                            }
                        },
                        "contract": {
                            "type": "object",
                            "properties": {
                                "duration": {"type": "integer"},
                                "payment_term": {"type": "string"},
                                "auto_activate": {"type": "boolean"}
                            }
                        }
                    }
                }
            },
            "users": {
                "type": "array",
                "description": "Array of user objects",
                "items": {
                    "type": "object",
                    "properties": {
                        "firstName": {"type": "string"},
                        "lastName": {"type": "string"},
                        "email": {"type": "string"},
                        "role": {"type": "string", "description": "account_admin or user"},
                        "package": {"type": "string", "description": "pro, basic, or metered"},
                        "extension": {"type": "string"},
                        "mobile": {"type": "string"}
                    }
                }
            },
            "phone_numbers": {
                "type": "array",
                "description": "Array of phone numbers in E.164 format (e.g., +14155551234)",
                "items": {"type": "string"}
            }
        },
        "required": ["opportunity_id", "account", "locations", "users"]
    }
)
async def save_bhive_provisioning_data(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save b-hive provisioning data to JSON file.

    The agent calls this tool after analyzing Salesforce data to create
    a structured JSON file that can be used for b-hive provisioning.

    Args:
        args: Dictionary containing opportunity_id, account, locations, users, phone_numbers

    Returns:
        Formatted response with file path and validation status
    """
    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    if not BHIVE_MCP_ENABLED:
        return _format_tool_response({
            "success": False,
            "error": "B-hive MCP integration is disabled. Set BHIVE_MCP_ENABLED=true to enable."
        })

    # LOGGING
    print(f"[Tool:save_bhive_provisioning_data] Called for opportunity: {opp_id}")

    # Validate required fields
    validation_errors = []
    warnings = []

    import re
    account = args.get('account', {})
    if not account.get('name'):
        validation_errors.append("Missing: account.name")

    # Validate domain is lowercase alphanumeric with hyphens only
    domain = account.get('domain', '')
    if not domain:
        validation_errors.append("Missing: account.domain")
    elif not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', domain):
        validation_errors.append(f"Invalid: account.domain must be lowercase alphanumeric with hyphens only (e.g., 'company-name'), got: '{domain}'")

    if not account.get('time_zone'):
        validation_errors.append("Missing: account.time_zone")

    locations = args.get('locations', [])
    if not locations:
        validation_errors.append("Missing: at least one location")
    else:
        for i, loc in enumerate(locations):
            if not loc.get('name'):
                validation_errors.append(f"Missing: locations[{i}].name")
            addr = loc.get('address', {})
            if not addr.get('address'):
                validation_errors.append(f"Missing: locations[{i}].address.address")
            if not addr.get('city'):
                validation_errors.append(f"Missing: locations[{i}].address.city")

            # Validate state code is exactly 2 characters
            state = addr.get('state', '')
            if not state:
                validation_errors.append(f"Missing: locations[{i}].address.state")
            elif len(str(state)) != 2:
                validation_errors.append(f"Invalid: locations[{i}].address.state must be 2-character code (e.g., 'IN', 'CA'), got: '{state}'")

            # Validate ZIP code is exactly 5 digits
            zip_code = addr.get('zip', '')
            if not zip_code:
                validation_errors.append(f"Missing: locations[{i}].address.zip")
            elif not re.match(r'^\d{5}$', str(zip_code)):
                validation_errors.append(f"Invalid: locations[{i}].address.zip must be 5-digit ZIP code (e.g., '46156'), got: '{zip_code}'")

    users = args.get('users', [])
    if not users:
        validation_errors.append("Missing: at least one user")
    else:
        for i, user in enumerate(users):
            if not user.get('firstName'):
                validation_errors.append(f"Missing: users[{i}].firstName")
            if not user.get('lastName'):
                validation_errors.append(f"Missing: users[{i}].lastName")
            if not user.get('email'):
                validation_errors.append(f"Missing: users[{i}].email")

    # Validate user-location mapping for multi-location accounts
    if len(locations) > 1 and users:
        location_names = {loc["name"].lower() for loc in locations}
        users_without_location = []
        users_with_invalid_location = []

        for i, user in enumerate(users):
            user_loc = user.get("location_name", "")
            if not user_loc:
                users_without_location.append(f"{user.get('firstName', '')} {user.get('lastName', '')} (users[{i}])")
            elif user_loc.lower() not in location_names:
                users_with_invalid_location.append(
                    f"{user.get('firstName', '')} {user.get('lastName', '')} - assigned to '{user_loc}' (users[{i}])"
                )

        if users_without_location:
            warnings.append(
                f"Multi-location account has {len(users_without_location)} users without location_name. "
                f"These will be assigned to the first location: {locations[0]['name']}. "
                f"Users: {', '.join(users_without_location[:5])}" +
                (f" and {len(users_without_location) - 5} more..." if len(users_without_location) > 5 else "")
            )
            # Auto-assign users without location to first location
            first_loc_name = locations[0]["name"]
            for user in users:
                if not user.get("location_name"):
                    user["location_name"] = first_loc_name

        if users_with_invalid_location:
            validation_errors.append(
                f"Users have invalid location_name values that don't match any location: "
                f"{', '.join(users_with_invalid_location[:3])}" +
                (f" and {len(users_with_invalid_location) - 3} more..." if len(users_with_invalid_location) > 3 else "")
            )

    phone_numbers = args.get('phone_numbers', [])
    if not phone_numbers:
        warnings.append("No phone numbers specified - account will be created without DIDs")

    # Build the provisioning data structure
    status = "ready" if not validation_errors else "incomplete"

    # Apply defaults to locations
    for loc in locations:
        if 'contract' not in loc:
            loc['contract'] = {}
        loc['contract'].setdefault('duration', BHIVE_DEFAULT_CONTRACT_DURATION)
        loc['contract'].setdefault('payment_term', BHIVE_DEFAULT_PAYMENT_TERM)
        loc['contract'].setdefault('auto_activate', BHIVE_AUTO_ACTIVATE_CONTRACT)

    data = {
        "opportunity_id": opp_id,
        "opportunity_name": args.get('opportunity_name', account.get('name', '')),
        "created_at": datetime.now().isoformat(),
        "status": status,
        "account": {
            "name": account.get('name', ''),
            "domain": account.get('domain', ''),
            "time_zone": account.get('time_zone', 'America/New_York'),
            "sales_channel_type": account.get('sales_channel_type', 'direct_sales')
        },
        "locations": locations,
        "users": users,
        "phone_numbers": phone_numbers,
        "validation": {
            "ready_for_provisioning": len(validation_errors) == 0,
            "missing_required": validation_errors,
            "warnings": warnings
        },
        "provisioning_result": None
    }

    # Save to file
    json_path = DATA_DIR / opp_id / BHIVE_PROVISIONING_FILE
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)

    # LOGGING
    print(f"[Tool:save_bhive_provisioning_data] ═══════════════════════════════════════")
    print(f"[Tool:save_bhive_provisioning_data] B-hive Provisioning Data Saved")
    print(f"[Tool:save_bhive_provisioning_data] ═══════════════════════════════════════")
    print(f"[Tool:save_bhive_provisioning_data] Status: {status}")
    print(f"[Tool:save_bhive_provisioning_data] Account: {account.get('name', 'N/A')}")
    print(f"[Tool:save_bhive_provisioning_data] Locations: {len(locations)}")
    print(f"[Tool:save_bhive_provisioning_data] Users: {len(users)}")
    print(f"[Tool:save_bhive_provisioning_data] Phone Numbers: {len(phone_numbers)}")
    if validation_errors:
        print(f"[Tool:save_bhive_provisioning_data] ❌ Validation errors: {len(validation_errors)}")
        for err in validation_errors[:5]:
            print(f"[Tool:save_bhive_provisioning_data]   - {err}")
    if warnings:
        print(f"[Tool:save_bhive_provisioning_data] ⚠️  Warnings: {len(warnings)}")
        for warn in warnings:
            print(f"[Tool:save_bhive_provisioning_data]   - {warn}")
    print(f"[Tool:save_bhive_provisioning_data] File: {json_path}")
    print(f"[Tool:save_bhive_provisioning_data] ═══════════════════════════════════════")

    return _format_tool_response({
        "success": True,
        "file_path": str(json_path),
        "status": status,
        "ready_for_provisioning": len(validation_errors) == 0,
        "validation_errors": validation_errors,
        "warnings": warnings,
        "stats": {
            "users": len(users),
            "locations": len(locations),
            "phone_numbers": len(phone_numbers)
        }
    })


def _interpret_provisioning_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Interpret B-hive provisioning result to distinguish partial success from failure.

    Account creation with some item-level errors (duplicates, missing DIDs) should
    still be reported as success since the core provisioning worked.
    """
    account = result.get("account", {})
    stats = result.get("stats", {})
    errors = result.get("errors", [])

    account_created = bool(account.get("id"))
    locations_created = stats.get("locations_created", 0)
    users_created = stats.get("users_created", 0)

    # Count error types by analyzing error messages
    error_str = str(errors).lower()
    duplicate_errors = error_str.count("already") + error_str.count("duplicate")
    did_errors = error_str.count("did") + error_str.count("inventory") + error_str.count("not found")

    if not account_created:
        return {
            "is_success": False,
            "severity": "critical",
            "summary": "Account creation failed",
            "recommendation": "Review error message and fix prerequisites"
        }

    if account_created and (locations_created > 0 or users_created > 0):
        return {
            "is_success": True,
            "severity": "info" if not errors else "warning",
            "summary": f"Account created successfully. {locations_created} locations, {users_created} users provisioned.",
            "recommendation": "Review any errors in B-hive console if needed" if errors else None,
            "expected_errors": {
                "duplicates": duplicate_errors,
                "missing_dids": did_errors
            }
        }

    return {
        "is_success": False,
        "severity": "error",
        "summary": "Provisioning completed but no resources created",
        "recommendation": "Check provisioning data and retry"
    }


@tool(
    "provision_to_bhive",
    "Execute b-hive provisioning. Reads bhive_provisioning_data.json and calls the MCP server to create the account, locations, users, and phone numbers.",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def provision_to_bhive(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute b-hive provisioning using the MCP server.

    Reads the bhive_provisioning_data.json file and calls the MCP server's
    provision_complete_customer tool to create the account.

    Supports cancellation via CancellationManager. WARNING: Once the provisioning
    request is sent to the server, cancellation will disconnect but the operation
    may still complete server-side.

    Args:
        args: Dictionary with 'opportunity_id'

    Returns:
        Formatted response with provisioning results
    """
    from bhive_client import BHiveMCPClient

    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    if not BHIVE_MCP_ENABLED:
        return _format_tool_response({
            "success": False,
            "error": "B-hive MCP integration is disabled"
        })

    # Get cancellation manager and set state
    cancellation_mgr = get_cancellation_manager()
    cancellation_mgr.set_state(OperationState.PROVISIONING_BHIVE)
    cancellation_mgr.set_opportunity_id(opp_id)

    # LOGGING
    print(f"[Tool:provision_to_bhive] Called for opportunity: {opp_id}")

    # Check for provisioning data file
    json_path = DATA_DIR / opp_id / BHIVE_PROVISIONING_FILE

    if not json_path.exists():
        cancellation_mgr.set_state(OperationState.IDLE)
        return _format_tool_response({
            "success": False,
            "error": f"No provisioning data found at {json_path}. Run save_bhive_provisioning_data first."
        })

    # Load provisioning data
    with open(json_path, 'r') as f:
        data = json.load(f)

    # Check if ready
    if data.get("status") != "ready":
        cancellation_mgr.set_state(OperationState.IDLE)
        return _format_tool_response({
            "success": False,
            "error": "Provisioning data not ready",
            "status": data.get("status"),
            "missing": data.get("validation", {}).get("missing_required", [])
        })

    # Check if already provisioned
    if data.get("status") == "provisioned":
        cancellation_mgr.set_state(OperationState.IDLE)
        return _format_tool_response({
            "success": False,
            "error": "This opportunity has already been provisioned",
            "provisioning_result": data.get("provisioning_result")
        })

    print(f"[Tool:provision_to_bhive] Connecting to b-hive MCP server...")
    print(f"[Tool:provision_to_bhive] URL: {BHIVE_MCP_SERVER_URL}/mcp/messages")

    # Create MCP client
    client = BHiveMCPClient()

    # Test connection
    conn_test = await client.test_connection()
    if not conn_test.get("success"):
        error_msg = conn_test.get('error', 'Unknown error')
        print(f"[Tool:provision_to_bhive] ❌ Connection failed: {error_msg}")
        print(f"[Tool:provision_to_bhive] Ensure MCP server is running with: ./bin/server_http")
        cancellation_mgr.set_state(OperationState.IDLE)
        return _format_tool_response({
            "success": False,
            "error": f"Cannot connect to b-hive MCP server: {error_msg}",
            "help": f"Ensure the MCP server is running with ./bin/server_http at {BHIVE_MCP_SERVER_URL}"
        })

    print(f"[Tool:provision_to_bhive] Connected to MCP server (Rails {conn_test.get('rails_version')})")
    print(f"[Tool:provision_to_bhive] Starting provisioning...")

    try:
        # Build locations with users and phone numbers
        # IMPORTANT: Filter users by location_name to avoid duplicates
        all_users = data.get("users", [])
        locations_list = data.get("locations", [])
        first_location_name = locations_list[0]["name"].lower() if locations_list else ""

        locations_payload = []
        for idx, loc in enumerate(locations_list):
            loc_name_lower = loc["name"].lower()

            # Filter users: only include users that belong to this location
            # Users without location_name go to the first location only
            location_users = [
                u for u in all_users
                if u.get("location_name", "").lower() == loc_name_lower
                or u.get("location_id") == loc.get("id")
                or (not u.get("location_name") and idx == 0)  # Unassigned users go to first location
            ]

            loc_payload = {
                "name": loc["name"],
                "address": loc["address"],
                "contract": loc.get("contract", {
                    "duration": BHIVE_DEFAULT_CONTRACT_DURATION,
                    "payment_term": BHIVE_DEFAULT_PAYMENT_TERM,
                    "auto_activate": BHIVE_AUTO_ACTIVATE_CONTRACT
                }),
                "users": location_users,
                "phone_numbers": data.get("phone_numbers", [])
            }
            locations_payload.append(loc_payload)

            if location_users:
                print(f"[Tool:provision_to_bhive] Location '{loc['name']}': {len(location_users)} users")

        # Get cancellation token for async operation
        cancel_event = cancellation_mgr.get_cancellation_token() if CANCELLATION_ENABLED else None

        # Call MCP server with cancellation support
        result = await client.provision_complete_customer(
            customer_name=data["account"]["name"],
            domain=data["account"]["domain"],
            time_zone=data["account"]["time_zone"],
            locations=locations_payload,
            sales_channel_type=data["account"].get("sales_channel_type", "direct_sales"),
            cancel_event=cancel_event
        )

        # Update JSON with result
        data["provisioning_result"] = result
        data["provisioned_at"] = datetime.now().isoformat()

        # Interpret the result to distinguish partial success from failure
        interpretation = _interpret_provisioning_result(result)

        if interpretation["is_success"]:
            data["status"] = "provisioned"
            print(f"[Tool:provision_to_bhive] ✅ {interpretation['summary']}")
        else:
            data["status"] = "failed"
            print(f"[Tool:provision_to_bhive] ❌ {interpretation['summary']}")

        # Save updated data
        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)

        # LOGGING
        print(f"[Tool:provision_to_bhive] ═══════════════════════════════════════")
        print(f"[Tool:provision_to_bhive] Provisioning Complete")
        print(f"[Tool:provision_to_bhive] ═══════════════════════════════════════")
        if result.get("account"):
            acc = result["account"]
            print(f"[Tool:provision_to_bhive] Account ID: {acc.get('id')}")
            print(f"[Tool:provision_to_bhive] Account Number: {acc.get('account_number')}")
            print(f"[Tool:provision_to_bhive] SIP Domain: {acc.get('sip_domain')}")
        if result.get("stats"):
            stats = result["stats"]
            print(f"[Tool:provision_to_bhive] Users Created: {stats.get('users_created', 0)}")
            print(f"[Tool:provision_to_bhive] Locations Created: {stats.get('locations_created', 0)}")
            print(f"[Tool:provision_to_bhive] Phone Numbers Assigned: {stats.get('phone_numbers_assigned', 0)}")
        if interpretation.get("expected_errors"):
            exp_err = interpretation["expected_errors"]
            if exp_err.get("duplicates", 0) > 0:
                print(f"[Tool:provision_to_bhive] Duplicate Errors (expected): {exp_err['duplicates']}")
            if exp_err.get("missing_dids", 0) > 0:
                print(f"[Tool:provision_to_bhive] Missing DIDs (can be added later): {exp_err['missing_dids']}")
        print(f"[Tool:provision_to_bhive] ═══════════════════════════════════════")

        return _format_tool_response({
            "success": interpretation["is_success"],
            "message": interpretation["summary"],
            "account": result.get("account"),
            "locations": result.get("locations"),
            "stats": result.get("stats"),
            "errors": result.get("errors", []),
            "interpretation": interpretation
        })

    except CancellationRequestedError:
        # Cancelled during provisioning - this is serious because the request may have been sent
        print(f"[Tool:provision_to_bhive] ⚠️ Cancelled during provisioning!")

        # Update status to cancelled with warning
        data["status"] = "cancelled"
        data["cancellation_warning"] = (
            "Provisioning was cancelled but the request may have been sent to the server. "
            "Check the BHive admin console to verify if the account was created."
        )
        data["cancelled_at"] = datetime.now().isoformat()

        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)

        return _format_tool_response({
            "success": False,
            "cancelled": True,
            "opportunity_id": opp_id,
            "warning": (
                "BHive provisioning was cancelled. WARNING: The provisioning request may have "
                "already been sent to the server. The operation could have completed server-side. "
                "Please check the BHive admin console to verify whether the account was created."
            ),
            "recommendation": "Check BHive admin console to verify account status before retrying."
        })

    except Exception as e:
        # Update status to failed
        data["status"] = "failed"
        data["provisioning_result"] = {"error": str(e)}

        with open(json_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"[Tool:provision_to_bhive] ❌ Error: {str(e)}")

        return _format_tool_response({
            "success": False,
            "error": str(e)
        })

    finally:
        # Reset state when done
        cancellation_mgr.set_state(OperationState.IDLE)


@tool(
    "check_bhive_provisioning_status",
    "Check status of an asynchronous b-hive provisioning job (for bulk user imports with 100+ users)",
    {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The async job ID returned from provisioning"
            }
        },
        "required": ["job_id"]
    }
)
async def check_bhive_provisioning_status(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check status of an asynchronous provisioning job.

    When provisioning 100+ users, the MCP server processes them asynchronously.
    This tool checks the status of such jobs.

    Args:
        args: Dictionary with 'job_id'

    Returns:
        Formatted response with job status and progress
    """
    from bhive_client import BHiveMCPClient

    job_id = args.get('job_id', '')

    if not job_id:
        return _format_tool_response({
            "success": False,
            "error": "No job_id provided"
        })

    if not BHIVE_MCP_ENABLED:
        return _format_tool_response({
            "success": False,
            "error": "B-hive MCP integration is disabled"
        })

    print(f"[Tool:check_bhive_provisioning_status] Checking job: {job_id}")

    client = BHiveMCPClient()

    try:
        result = await client.get_provisioning_status(job_id)

        print(f"[Tool:check_bhive_provisioning_status] Status: {result.get('status')}")
        print(f"[Tool:check_bhive_provisioning_status] Progress: {result.get('progress', 0)}%")

        return _format_tool_response({
            "success": True,
            "job_id": job_id,
            "status": result.get("status"),
            "progress": result.get("progress", 0),
            "message": result.get("message", ""),
            "error": result.get("error")
        })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


@tool(
    "generate_bhive_report",
    "Generate a comprehensive b-hive provisioning status report in Markdown format",
    {
        "type": "object",
        "properties": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        },
        "required": ["opportunity_id"]
    }
)
async def generate_bhive_report(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a b-hive provisioning status report.

    Creates a Markdown report with details about the provisioning result,
    including account details, created resources, and any errors.

    Args:
        args: Dictionary with 'opportunity_id'

    Returns:
        Formatted response with report file path
    """
    opp_id = args.get('opportunity_id', '')

    if not opp_id:
        return _format_tool_response({
            "success": False,
            "error": "No opportunity_id provided"
        })

    # Check for provisioning data file
    json_path = DATA_DIR / opp_id / BHIVE_PROVISIONING_FILE

    if not json_path.exists():
        return _format_tool_response({
            "success": False,
            "error": f"No provisioning data found at {json_path}"
        })

    # Load provisioning data
    with open(json_path, 'r') as f:
        data = json.load(f)

    print(f"[Tool:generate_bhive_report] Generating report for: {opp_id}")

    # Build report
    report_lines = [
        f"# B-hive Provisioning Report",
        f"",
        f"**Opportunity:** {data.get('opportunity_name', 'N/A')} ({opp_id})",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Status:** {data.get('status', 'unknown').upper()}",
        f"",
        f"---",
        f"",
        f"## Account Details",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Company Name | {data.get('account', {}).get('name', 'N/A')} |",
        f"| SIP Domain | {data.get('account', {}).get('domain', 'N/A')} |",
        f"| Time Zone | {data.get('account', {}).get('time_zone', 'N/A')} |",
        f"| Sales Channel | {data.get('account', {}).get('sales_channel_type', 'N/A')} |",
        f"",
    ]

    # Provisioning result section
    prov_result = data.get('provisioning_result')
    if prov_result:
        report_lines.extend([
            f"## Provisioning Result",
            f"",
        ])

        if prov_result.get('account'):
            acc = prov_result['account']
            report_lines.extend([
                f"### Account Created",
                f"",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| Account ID | {acc.get('id', 'N/A')} |",
                f"| Account Number | {acc.get('account_number', 'N/A')} |",
                f"| SIP Domain | {acc.get('sip_domain', 'N/A')} |",
                f"",
            ])

        if prov_result.get('stats'):
            stats = prov_result['stats']
            report_lines.extend([
                f"### Summary",
                f"",
                f"| Resource | Count |",
                f"|----------|-------|",
                f"| Accounts Created | {stats.get('accounts_created', 0)} |",
                f"| Locations Created | {stats.get('locations_created', 0)} |",
                f"| Contracts Created | {stats.get('contracts_created', 0)} |",
                f"| Users Created | {stats.get('users_created', 0)} |",
                f"| Phone Numbers Assigned | {stats.get('phone_numbers_assigned', 0)} |",
                f"",
            ])

        if prov_result.get('errors'):
            report_lines.extend([
                f"### Errors",
                f"",
            ])
            for error in prov_result['errors']:
                report_lines.append(f"- {error}")
            report_lines.append("")
    else:
        report_lines.extend([
            f"## Provisioning Result",
            f"",
            f"_Not yet provisioned_",
            f"",
        ])

    # Locations section
    report_lines.extend([
        f"## Locations ({len(data.get('locations', []))})",
        f"",
    ])

    for i, loc in enumerate(data.get('locations', []), 1):
        addr = loc.get('address', {})
        contract = loc.get('contract', {})
        report_lines.extend([
            f"### {i}. {loc.get('name', 'Unnamed Location')}",
            f"",
            f"**Address:** {addr.get('address', '')}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('zip', '')}",
            f"",
            f"**Contract:** {contract.get('duration', 12)} months, {contract.get('payment_term', 'monthly')}",
            f"",
        ])

    # Users section
    report_lines.extend([
        f"## Users ({len(data.get('users', []))})",
        f"",
        f"| Name | Email | Role | Package |",
        f"|------|-------|------|---------|",
    ])

    for user in data.get('users', []):
        name = f"{user.get('firstName', '')} {user.get('lastName', '')}"
        report_lines.append(f"| {name} | {user.get('email', 'N/A')} | {user.get('role', 'user')} | {user.get('package', 'pro')} |")

    report_lines.append("")

    # Phone numbers section
    phone_numbers = data.get('phone_numbers', [])
    report_lines.extend([
        f"## Phone Numbers ({len(phone_numbers)})",
        f"",
    ])

    if phone_numbers:
        for phone in phone_numbers:
            report_lines.append(f"- {phone}")
    else:
        report_lines.append("_No phone numbers specified_")

    report_lines.extend([
        f"",
        f"---",
        f"",
        f"*Report generated by BV Provisioning Agent*",
    ])

    # Save report
    provs_dir = DATA_DIR / opp_id / 'provs'
    provs_dir.mkdir(parents=True, exist_ok=True)
    report_path = provs_dir / f"{opp_id}_bhive_provisioning.md"

    with open(report_path, 'w') as f:
        f.write('\n'.join(report_lines))

    print(f"[Tool:generate_bhive_report] Report saved to: {report_path}")

    return _format_tool_response({
        "success": True,
        "report_file": str(report_path),
        "message": f"B-hive provisioning report created: {report_path}"
    })


@tool(
    "cancel_operation",
    "Cancel the currently running long operation (Salesforce extraction or BHive provisioning). Requires confirmation.",
    {
        "type": "object",
        "properties": {
            "confirmation": {
                "type": "boolean",
                "description": "Set to true to confirm the cancellation. Without confirmation, returns current operation status."
            }
        },
        "required": []
    }
)
async def cancel_operation(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cancel the currently running operation.

    This tool allows Claude to cancel long-running operations like Salesforce
    extraction or BHive provisioning. It requires explicit confirmation.

    Args:
        args: Dictionary with optional 'confirmation' boolean

    Returns:
        Formatted response with cancellation status
    """
    if not CANCELLATION_ENABLED:
        return _format_tool_response({
            "success": False,
            "error": "Cancellation is disabled in configuration"
        })

    cancellation_mgr = get_cancellation_manager()
    confirmation = args.get('confirmation', False)

    # Check if an operation is running
    if not cancellation_mgr.is_operation_running():
        return _format_tool_response({
            "success": False,
            "error": "No operation is currently running to cancel."
        })

    # Get current state info
    current_state = cancellation_mgr.get_current_state()
    opportunity_id = cancellation_mgr.get_opportunity_id()

    state_descriptions = {
        OperationState.EXTRACTING_SALESFORCE: "Salesforce data extraction",
        OperationState.ANALYZING_DOCUMENTS: "document analysis",
        OperationState.PROVISIONING_BHIVE: "BHive provisioning",
        OperationState.GENERATING_CSV: "CSV generation",
        OperationState.GENERATING_REPORT: "report generation",
    }
    state_desc = state_descriptions.get(current_state, current_state.value)

    # If no confirmation, return status and request confirmation
    if not confirmation:
        message = f"Currently running: {state_desc}"
        if opportunity_id:
            message += f" for opportunity {opportunity_id}"
        message += ". Call with confirmation=true to cancel."

        # Add BHive warning
        if current_state == OperationState.PROVISIONING_BHIVE:
            message += (
                " WARNING: BHive provisioning cannot be stopped mid-flight. "
                "If cancelled, the request may have already been sent and could complete server-side."
            )

        return _format_tool_response({
            "success": True,
            "requires_confirmation": True,
            "current_operation": current_state.value,
            "opportunity_id": opportunity_id,
            "message": message
        })

    # Execute cancellation
    result = cancellation_mgr.request_cancellation()
    if result.get("pending"):
        # Auto-confirm since Claude explicitly passed confirmation=true
        result = cancellation_mgr.confirm_cancellation()

    return _format_tool_response({
        "success": True,
        "cancelled": True,
        "previous_operation": current_state.value,
        "opportunity_id": opportunity_id,
        "message": result.get("message", "Operation cancelled."),
        "bhive_warning": current_state == OperationState.PROVISIONING_BHIVE
    })


# Export all tool functions for registration
ALL_TOOLS = [
    extract_salesforce_data,
    analyze_documents,
    validate_attributes,
    generate_provisioning_csv,
    generate_status_report,
    query_salesforce_general,
    check_extraction_status,
    read_provisioning_file,
    queue_file_for_teams,
    # B-hive provisioning tools
    save_bhive_provisioning_data,
    provision_to_bhive,
    check_bhive_provisioning_status,
    generate_bhive_report,
    # Cancellation tool
    cancel_operation
]

# Tool metadata for SDK registration
TOOL_SCHEMAS = {
    "extract_salesforce_data": {
        "description": "Extract comprehensive Salesforce data for an opportunity including contacts, documents, transcripts, and relationships",
        "input_schema": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID (18 characters starting with 006)"
            }
        }
    },
    "analyze_documents": {
        "description": "Analyze Excel/spreadsheet documents to extract user lists, device inventories, and other structured data",
        "input_schema": {
            "documents_directory": {
                "type": "string",
                "description": "Path to the documents directory containing spreadsheets"
            }
        }
    },
    "validate_attributes": {
        "description": "Validate extracted attributes against the 80-attribute requirements template",
        "input_schema": {
            "attributes_data": {
                "type": "object",
                "description": "Dictionary of extracted attributes with their values, sources, and statuses"
            }
        }
    },
    "generate_provisioning_csv": {
        "description": "Generate the final provisioning CSV file with all 80 attributes",
        "input_schema": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            },
            "attributes_data": {
                "type": "object",
                "description": "Dictionary of extracted attributes with their values, sources, and statuses"
            }
        }
    },
    "generate_status_report": {
        "description": "Generate comprehensive status report in Markdown format",
        "input_schema": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            },
            "opportunity_name": {
                "type": "string",
                "description": "The opportunity name/customer name"
            },
            "validation_results": {
                "type": "object",
                "description": "Results from attribute validation"
            },
            "data_sources": {
                "type": "object",
                "description": "Information about data sources analyzed"
            }
        }
    },
    "query_salesforce_general": {
        "description": "Execute general Salesforce queries using sf CLI - search opportunities, accounts, contacts by name or run SOQL queries",
        "input_schema": {
            "query_type": {
                "type": "string",
                "description": "Type of query: 'search' for text search or 'soql' for SOQL query"
            },
            "query": {
                "type": "string",
                "description": "Search term (for search) or SOQL query string (for soql)"
            },
            "object_type": {
                "type": "string",
                "description": "Salesforce object type (e.g., Opportunity, Account, Contact) - only used for search"
            }
        }
    },
    "check_extraction_status": {
        "description": "Check if provisioning files exist for an opportunity and return status metrics",
        "input_schema": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        }
    },
    "read_provisioning_file": {
        "description": "Read and parse an existing provisioning CSV file to show extracted attributes",
        "input_schema": {
            "opportunity_id": {
                "type": "string",
                "description": "The Salesforce opportunity ID"
            }
        }
    }
}
