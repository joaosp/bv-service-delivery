"""
Utility Functions

Common utility functions for the Salesforce extractors package.
"""

import json
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union


def setup_directories(base_path: Union[str, Path], opp_id: str) -> Path:
    """
    Create directory structure for opportunity data
    
    Args:
        base_path: Base directory path
        opp_id: Opportunity ID
        
    Returns:
        Path to the created data directory
    """
    data_dir = Path(base_path) / "data" / opp_id
    
    # Create main directories
    directories = [
        "",  # Base data directory
        "documents",
        "documents/quotes",
        "documents/contracts", 
        "documents/emails",
        "documents/spreadsheets",
        "documents/pdfs",
        "documents/documents",
        "documents/images",
        "documents/other",
        "transcripts",
        "transcripts/raw",
        "transcripts/cleaned"
    ]
    
    for directory in directories:
        dir_path = data_dir / directory
        dir_path.mkdir(parents=True, exist_ok=True)
    
    return data_dir


def clean_filename(filename: str, max_length: int = 100) -> str:
    """
    Clean filename for safe file system storage
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
        
    Returns:
        Cleaned filename
    """
    if not filename:
        return "untitled"
    
    # Remove or replace invalid characters
    safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    safe_filename = re.sub(r'[^\w\s\-_.]', '', safe_filename)
    safe_filename = re.sub(r'\s+', ' ', safe_filename).strip()
    
    # Remove leading/trailing dots and spaces
    safe_filename = safe_filename.strip('. ')
    
    # Ensure we have something
    if not safe_filename:
        safe_filename = "untitled"
    
    # Truncate if too long, preserving extension
    if len(safe_filename) > max_length:
        name, ext = os.path.splitext(safe_filename)
        available_length = max_length - len(ext)
        if available_length > 0:
            safe_filename = name[:available_length] + ext
        else:
            safe_filename = safe_filename[:max_length]
    
    return safe_filename


def save_json(data: Any, filepath: Union[str, Path], indent: int = 2) -> bool:
    """
    Save data as JSON file
    
    Args:
        data: Data to save
        filepath: Output file path
        indent: JSON indentation
        
    Returns:
        True if successful, False otherwise
    """
    try:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, default=str, ensure_ascii=False)
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving JSON to {filepath}: {str(e)}")
        return False


def load_json(filepath: Union[str, Path]) -> Optional[Dict]:
    """
    Load data from JSON file
    
    Args:
        filepath: Path to JSON file
        
    Returns:
        Loaded data or None if failed
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading JSON from {filepath}: {str(e)}")
        return None


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        Formatted file size string
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"


def calculate_extraction_metrics(stats_dict: Dict) -> Dict:
    """
    Calculate combined extraction metrics from extractor stats dictionary
    
    Args:
        stats_dict: Dictionary of extraction stats from different extractors
        
    Returns:
        Combined metrics dictionary
    """
    combined_metrics = {
        "total_queries": 0,
        "total_api_requests": 0,
        "total_errors": 0,
        "total_duration": 0,
        "start_time": None,
        "end_time": datetime.now().isoformat(),
        "all_errors": []
    }
    
    earliest_start = None
    
    # Process each component's stats
    for component_name, stats in stats_dict.items():
        if not stats or not isinstance(stats, dict):
            continue
        
        # Aggregate numbers
        combined_metrics["total_queries"] += stats.get("queries_executed", 0)
        combined_metrics["total_api_requests"] += stats.get("api_requests", 0)
        combined_metrics["total_errors"] += len(stats.get("errors", []))
        
        # Track earliest start time
        start_time = stats.get("start_time")
        if start_time:
            if earliest_start is None or start_time < earliest_start:
                earliest_start = start_time
        
        # Collect all errors
        errors = stats.get("errors", [])
        combined_metrics["all_errors"].extend(errors)
    
    # Set start time and calculate duration
    if earliest_start:
        combined_metrics["start_time"] = earliest_start
        start_dt = datetime.fromisoformat(earliest_start)
        end_dt = datetime.fromisoformat(combined_metrics["end_time"])
        combined_metrics["total_duration"] = (end_dt - start_dt).total_seconds()
    
    return combined_metrics


def validate_opportunity_id(opp_id: str) -> bool:
    """
    Validate Salesforce opportunity ID format
    
    Args:
        opp_id: Opportunity ID to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not opp_id:
        return False
    
    # Salesforce IDs are either 15 or 18 characters
    if len(opp_id) not in [15, 18]:
        return False
    
    # Should be alphanumeric
    if not re.match(r'^[a-zA-Z0-9]+$', opp_id):
        return False
    
    # Opportunity IDs typically start with "006"
    if not opp_id.startswith('006'):
        return False
    
    return True


def extract_id_from_url(url: str) -> Optional[str]:
    """
    Extract Salesforce ID from URL
    
    Args:
        url: Salesforce URL
        
    Returns:
        Extracted ID or None
    """
    if not url:
        return None
    
    # Look for 15 or 18 character IDs in URL
    id_pattern = r'[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?'
    matches = re.findall(id_pattern, url)
    
    for match in matches:
        if len(match) in [15, 18]:
            return match
    
    return None


def merge_dictionaries(*dicts: Dict) -> Dict:
    """
    Merge multiple dictionaries, with later ones taking precedence
    
    Args:
        *dicts: Dictionaries to merge
        
    Returns:
        Merged dictionary
    """
    result = {}
    
    for d in dicts:
        if d:
            result.update(d)
    
    return result


def safe_get_nested(data: Dict, path: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary value using dot notation
    
    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "Contact.Name")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    try:
        keys = path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
        
    except Exception:
        return default


def chunk_list(items: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks of specified size
    
    Args:
        items: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    chunks = []
    for i in range(0, len(items), chunk_size):
        chunks.append(items[i:i + chunk_size])
    return chunks


def deduplicate_records(records: List[Dict], key_field: str = "Id") -> List[Dict]:
    """
    Remove duplicate records based on key field
    
    Args:
        records: List of records
        key_field: Field to use for deduplication
        
    Returns:
        Deduplicated list
    """
    seen = set()
    unique_records = []
    
    for record in records:
        key_value = record.get(key_field)
        if key_value and key_value not in seen:
            seen.add(key_value)
            unique_records.append(record)
    
    return unique_records


def format_phone_number(phone: str) -> str:
    """
    Format phone number for consistency
    
    Args:
        phone: Raw phone number
        
    Returns:
        Formatted phone number
    """
    if not phone:
        return ""
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    # Format US numbers
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    else:
        return phone  # Return original if can't format


def extract_email_domain(email: str) -> str:
    """
    Extract domain from email address
    
    Args:
        email: Email address
        
    Returns:
        Domain part of email
    """
    if not email or '@' not in email:
        return ""
    
    try:
        return email.split('@')[1].lower()
    except IndexError:
        return ""


def create_summary_stats(data: Dict) -> Dict:
    """
    Create summary statistics from extracted data
    
    Args:
        data: Extracted data dictionary
        
    Returns:
        Summary statistics
    """
    stats = {
        "totals": {
            "contacts": 0,
            "documents": 0,
            "transcripts": 0,
            "tasks": 0,
            "events": 0,
            "cases": 0,
            "notes": 0
        },
        "data_quality": {
            "contacts_with_email": 0,
            "contacts_with_phone": 0,
            "documents_downloaded": 0,
            "transcripts_cleaned": 0
        },
        "key_metrics": {}
    }
    
    # Count totals from actual data structure
    contacts_data = data.get("contacts", {})
    contacts = contacts_data.get("contacts", [])
    stats["totals"]["contacts"] = len(contacts)
    
    # Add contact roles count
    contact_roles = contacts_data.get("contact_roles", [])
    stats["totals"]["contact_roles"] = len(contact_roles)
    
    documents_data = data.get("documents", {})
    # Count total documents (successful + skipped + failed)
    doc_stats = documents_data.get("stats", {})
    total_docs = doc_stats.get("successful", 0) + doc_stats.get("skipped", 0) + doc_stats.get("failed", 0)
    if total_docs == 0:
        # Fallback to total_documents if available
        total_docs = doc_stats.get("total_documents", 0)
    stats["totals"]["documents"] = total_docs
    
    transcripts_data = data.get("transcripts", {})
    stats["totals"]["transcripts"] = transcripts_data.get("stats", {}).get("transcripts_extracted", 0)
    
    relationships_data = data.get("relationships", {})
    hierarchy = relationships_data.get("hierarchy", {}).get("direct_children", {})
    opp_children = hierarchy.get("opportunity", {})
    account_children = hierarchy.get("account", {})
    
    stats["totals"]["tasks"] = len(opp_children.get("tasks", []))
    stats["totals"]["events"] = len(opp_children.get("events", []))
    stats["totals"]["cases"] = len(account_children.get("cases", []))
    
    # Count notes from relationships
    notes = relationships_data.get("objects", {}).get("notes", [])
    stats["totals"]["notes"] = len(notes)
    
    # Data quality metrics
    for contact in contacts:
        if contact.get("Email"):
            stats["data_quality"]["contacts_with_email"] += 1
        if contact.get("Phone"):
            stats["data_quality"]["contacts_with_phone"] += 1
    
    stats["data_quality"]["documents_downloaded"] = documents_data.get("stats", {}).get("successful", 0)
    stats["data_quality"]["transcripts_cleaned"] = transcripts_data.get("stats", {}).get("transcripts_cleaned", 0)
    
    return stats


def log_extraction_summary(stats: Dict, output_dir: Path):
    """
    Log extraction summary to console and file
    
    Args:
        stats: Summary statistics
        output_dir: Output directory
    """
    print("\n" + "=" * 60)
    print("📊 EXTRACTION SUMMARY")
    print("=" * 60)
    
    totals = stats.get("totals", {})
    quality = stats.get("data_quality", {})
    
    print(f"📋 Data Extracted:")
    print(f"   - Contacts: {totals.get('contacts', 0)}")
    print(f"   - Documents: {totals.get('documents', 0)}")
    print(f"   - Transcripts: {totals.get('transcripts', 0)}")
    print(f"   - Tasks: {totals.get('tasks', 0)}")
    print(f"   - Events: {totals.get('events', 0)}")
    print(f"   - Cases: {totals.get('cases', 0)}")
    
    print(f"\n🎯 Data Quality:")
    print(f"   - Contacts with email: {quality.get('contacts_with_email', 0)}")
    print(f"   - Contacts with phone: {quality.get('contacts_with_phone', 0)}")
    print(f"   - Documents downloaded: {quality.get('documents_downloaded', 0)}")
    print(f"   - Transcripts cleaned: {quality.get('transcripts_cleaned', 0)}")
    
    print(f"\n📁 Output Directory: {output_dir}")
    print("=" * 60)
    
    # Save summary to file
    summary_file = output_dir / "extraction_summary.json"
    save_json(stats, summary_file)


def is_valid_email(email: str) -> bool:
    """
    Basic email validation
    
    Args:
        email: Email address to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not email:
        return False
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent processing
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    if not text:
        return ""
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    return text