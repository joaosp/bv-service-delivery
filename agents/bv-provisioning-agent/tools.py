"""
Custom tools for BV Provisioning Agent using Claude Agent SDK
"""
import subprocess
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
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
    DATA_DIR
)


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
    Extract comprehensive Salesforce data for an opportunity

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

    try:
        # Run the modular extraction script
        cmd = [
            'python3',
            str(EXTRACTION_SCRIPT),
            '--opp-id', opp_id
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

        # Determine output directory
        data_dir = PROJECT_ROOT / 'data' / opp_id

        return _format_tool_response({
            "success": True,
            "opportunity_id": opp_id,
            "output_directory": str(data_dir),
            "extraction_output": result.stdout,
            "files_created": {
                "opportunity": str(data_dir / "opportunity.json"),
                "contacts": str(data_dir / "contacts.json"),
                "documents": str(data_dir / "documents.json"),
                "transcripts": str(data_dir / "transcripts.json"),
                "relationships": str(data_dir / "relationships.json"),
                "summary": str(data_dir / "summary.md"),
                "complete_data": str(data_dir / "complete_data.json")
            }
        })

    except Exception as e:
        return _format_tool_response({
            "success": False,
            "error": str(e)
        })


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

    if not docs_dir.exists():
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
            return _format_tool_response({
                "success": True,
                "files_analyzed": [],
                "message": "No spreadsheets directory found"
            })

        # Find all Excel files
        excel_files = list(spreadsheets_dir.glob('*.xlsx')) + list(spreadsheets_dir.glob('*.xls'))

        for excel_file in excel_files:
            try:
                # Read Excel file
                df = pd.read_excel(excel_file, sheet_name=None)  # Read all sheets

                file_data = {
                    "file_path": str(excel_file),
                    "sheets": {}
                }

                for sheet_name, sheet_df in df.items():
                    # Convert to dictionary for easier processing
                    sheet_data = sheet_df.to_dict('records')
                    file_data["sheets"][sheet_name] = {
                        "row_count": len(sheet_data),
                        "columns": list(sheet_df.columns),
                        "sample_data": sheet_data[:5] if sheet_data else []  # First 5 rows as sample
                    }

                results["files_analyzed"].append(excel_file.name)
                results["data_extracted"][excel_file.name] = file_data

            except Exception as e:
                results["files_analyzed"].append(f"{excel_file.name} (ERROR: {str(e)})")

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

    try:
        # Load requirements template
        requirements = []
        with open(REQUIREMENTS_CSV, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            requirements = list(reader)

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

    try:
        # Create provs directory
        provs_dir = PROJECT_ROOT / 'data' / opp_id / 'provs'
        provs_dir.mkdir(parents=True, exist_ok=True)

        csv_file = provs_dir / f"{opp_id}_provisioning.csv"

        # Load requirements template to ensure all 80 attributes
        requirements = []
        with open(REQUIREMENTS_CSV, 'r') as f:
            reader = csv.DictReader(f, delimiter=';')
            requirements = list(reader)

        # Write provisioning CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=CSV_DELIMITER)
            writer.writeheader()

            for req in requirements:
                category = req['Category']
                attribute = req['Attribute']
                sub_attribute = req.get('Sub-Attribute', '')
                required = req['Required/Optional']

                # Get extracted data
                attr_key = f"{category}|{attribute}"
                if sub_attribute:
                    attr_key = f"{category}|{attribute}|{sub_attribute}"

                extracted = attributes_data.get(attr_key, {})

                row = {
                    'Category': category,
                    'Attribute': attribute,
                    'Sub-Attribute': sub_attribute,
                    'Required/Optional': required,
                    'Extracted Value': extracted.get('value', ''),
                    'Source Timestamp': extracted.get('source', ''),
                    'Status': extracted.get('status', 'Missing'),
                    'Notes': extracted.get('notes', '')
                }

                writer.writerow(row)

        return _format_tool_response({
            "success": True,
            "csv_file": str(csv_file),
            "rows_written": len(requirements),
            "message": f"Provisioning CSV created successfully: {csv_file}"
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
        # Create provs directory
        provs_dir = PROJECT_ROOT / 'data' / opp_id / 'provs'
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


# Export all tool functions for registration
ALL_TOOLS = [
    extract_salesforce_data,
    analyze_documents,
    validate_attributes,
    generate_provisioning_csv,
    generate_status_report,
    query_salesforce_general,
    check_extraction_status,
    read_provisioning_file
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
