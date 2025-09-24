"""
Report Generator

Generates comprehensive reports with Mermaid diagrams and visualizations
for Salesforce opportunity data extraction results.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import json


class ReportGenerator:
    """Generates reports and visualizations from extracted Salesforce data"""
    
    def __init__(self):
        self.report_data = {}
    
    def generate_relationship_diagram(self, opportunity_data: Dict, 
                                    contacts_data: Dict, 
                                    documents_data: Dict,
                                    relationships_data: Dict) -> str:
        """
        Generate Mermaid relationship diagram
        
        Args:
            opportunity_data: Opportunity and account data
            contacts_data: Contact data and roles
            documents_data: Document inventory
            relationships_data: Related objects data
            
        Returns:
            Mermaid diagram markup
        """
        lines = ["```mermaid", "graph TD"]
        
        # Account and Opportunity nodes
        account_name = opportunity_data.get("account", {}).get("Name", "Account")
        opp_name = opportunity_data.get("opportunity", {}).get("Name", "Opportunity")
        
        # Clean names for Mermaid (remove quotes and special chars)
        account_safe = self._clean_name_for_mermaid(account_name)
        opp_safe = self._clean_name_for_mermaid(opp_name)
        
        lines.append(f'    Account["{account_safe}"] --> Opp["{opp_safe}"]')
        
        # Contact nodes (limit to top 5)
        contacts = contacts_data.get("contacts", [])[:5]
        for i, contact in enumerate(contacts, 1):
            first_name = contact.get("FirstName", "")
            last_name = contact.get("LastName", "")
            title = contact.get("Title", "Contact")
            
            name = f"{first_name} {last_name}".strip()
            if not name:
                name = "Contact"
            
            contact_safe = self._clean_name_for_mermaid(name)
            title_safe = self._clean_name_for_mermaid(title) if title else "Contact"
            
            lines.append(f'    Opp --> Contact{i}["{contact_safe}<br/>{title_safe}"]')
        
        # Document type nodes
        doc_inventory = documents_data.get("inventory", {})
        doc_types = doc_inventory.get("by_type", {})
        
        for doc_type, info in list(doc_types.items())[:5]:  # Limit to 5 types
            count = info.get("count", 0)
            type_safe = self._clean_name_for_mermaid(doc_type.title())
            lines.append(f'    Opp --> Docs_{doc_type}["{count} {type_safe} files"]')
        
        # Activity nodes
        hierarchy = relationships_data.get("hierarchy", {})
        opp_children = hierarchy.get("direct_children", {}).get("opportunity", {})
        
        tasks = opp_children.get("tasks", [])
        events = opp_children.get("events", [])
        cases = hierarchy.get("direct_children", {}).get("account", {}).get("cases", [])
        
        if tasks:
            lines.append(f'    Opp --> Tasks["{len(tasks)} Tasks"]')
        
        if events:
            lines.append(f'    Opp --> Events["{len(events)} Events"]')
        
        if cases:
            lines.append(f'    Account --> Cases["{len(cases)} Cases"]')
        
        # Styling
        lines.extend([
            "",
            "    style Account fill:#e1f5fe",
            "    style Opp fill:#fff3e0",
            "    style Tasks fill:#f3e5f5",
            "    style Events fill:#f3e5f5",
            "    style Cases fill:#e8f5e9"
        ])
        
        lines.append("```")
        return "\n".join(lines)
    
    def generate_completeness_chart(self, all_data: Dict) -> str:
        """
        Generate data completeness pie chart
        
        Args:
            all_data: Complete extracted data dictionary
            
        Returns:
            Mermaid pie chart markup
        """
        # Collect data points from the actual data structure
        contacts_data = all_data.get("contacts", {})
        contacts_count = len(contacts_data.get("contacts", []))
        
        documents_data = all_data.get("documents", {})
        # Count total documents (successful + skipped + failed)
        stats = documents_data.get("stats", {})
        documents_count = stats.get("successful", 0) + stats.get("skipped", 0) + stats.get("failed", 0)
        if documents_count == 0:
            # Fallback to total_documents if available
            documents_count = stats.get("total_documents", 0)
        
        transcripts_data = all_data.get("transcripts", {})
        transcripts_count = transcripts_data.get("stats", {}).get("transcripts_extracted", 0)
        
        relationships_data = all_data.get("relationships", {})
        hierarchy = relationships_data.get("hierarchy", {}).get("direct_children", {})
        tasks_count = len(hierarchy.get("opportunity", {}).get("tasks", []))
        events_count = len(hierarchy.get("opportunity", {}).get("events", []))
        
        lines = [
            "```mermaid",
            "pie title Data Extraction Overview"
        ]
        
        if contacts_count > 0:
            lines.append(f'    "Contacts" : {contacts_count}')
        if documents_count > 0:
            lines.append(f'    "Documents" : {documents_count}')
        if transcripts_count > 0:
            lines.append(f'    "Transcripts" : {transcripts_count}')
        if tasks_count > 0:
            lines.append(f'    "Tasks" : {tasks_count}')
        if events_count > 0:
            lines.append(f'    "Events" : {events_count}')
        
        # If no data, show empty state
        if not any([contacts_count, documents_count, transcripts_count, tasks_count, events_count]):
            lines.append('    "No Data" : 1')
        
        lines.append("```")
        return "\n".join(lines)
    
    def generate_timeline(self, opportunity_data: Dict, extraction_time: datetime) -> str:
        """
        Generate timeline Gantt chart
        
        Args:
            opportunity_data: Opportunity data
            extraction_time: Time of extraction
            
        Returns:
            Mermaid Gantt chart markup
        """
        opp = opportunity_data.get("opportunity", {})
        created_date = opp.get("CreatedDate", "")[:10]  # Just date part
        close_date = opp.get("CloseDate", "")
        extraction_date = extraction_time.strftime("%Y-%m-%d")
        
        lines = [
            "```mermaid",
            "gantt",
            "    title Opportunity Timeline",
            "    dateFormat YYYY-MM-DD",
            "    section Lifecycle"
        ]
        
        if created_date:
            lines.append(f"    Opportunity Created    :done, opp1, {created_date}, 1d")
        
        lines.append(f"    Data Extraction       :active, extract, {extraction_date}, 1d")
        
        lines.extend([
            "    section Analysis",
            "    LLM Processing        :planned, after extract, 2d",
            "    Provisioning Creation :planned, after extract, 3d"
        ])
        
        lines.append("```")
        return "\n".join(lines)
    
    def generate_process_flow(self) -> str:
        """
        Generate extraction process flow diagram
        
        Returns:
            Mermaid flowchart markup
        """
        return """```mermaid
flowchart LR
    Start[Opportunity ID/Name] --> Query[Query Salesforce]
    Query --> Account[Get Account]
    Query --> Contacts[Get Contacts]
    Query --> Objects[Map Related Objects]
    Account --> Download[Download Documents]
    Contacts --> Download
    Objects --> Download
    Download --> Transcripts[Extract Transcripts]
    Transcripts --> Clean[Clean Transcripts]
    Clean --> Report[Generate Reports]
    Report --> Package[📦 Data Package Ready]
    
    style Start fill:#e8f5e9
    style Package fill:#c8e6c9
```"""
    
    def generate_activity_chart(self, relationships_data: Dict) -> str:
        """
        Generate activity analysis chart
        
        Args:
            relationships_data: Relationship mapping data
            
        Returns:
            Mermaid chart showing activity patterns
        """
        analysis = relationships_data.get("analysis", {})
        activity_patterns = analysis.get("activity_patterns", {})
        activity_types = activity_patterns.get("activity_types", {})
        
        if not activity_types:
            return ""
        
        lines = [
            "```mermaid",
            "pie title Activity Types Distribution"
        ]
        
        for activity_type, count in sorted(activity_types.items(), key=lambda x: x[0] or ""):
            if count > 0:
                type_clean = self._clean_name_for_mermaid(activity_type)
                lines.append(f'    "{type_clean}" : {count}')
        
        lines.append("```")
        return "\n".join(lines)
    
    def create_summary_report(self, all_data: Dict, output_path: Path) -> bool:
        """
        Create comprehensive markdown summary report
        
        Args:
            all_data: All extracted data
            output_path: Path to save the report
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract data components
            opportunity_data = all_data.get("opportunity", {})
            contacts_data = all_data.get("contacts", {})
            documents_data = all_data.get("documents", {})
            transcripts_data = all_data.get("transcripts", {})
            relationships_data = all_data.get("relationships", {})
            extraction_stats = all_data.get("extraction_stats", {})
            
            # Generate diagrams
            relationship_diagram = self.generate_relationship_diagram(
                opportunity_data, contacts_data, documents_data, relationships_data
            )
            completeness_chart = self.generate_completeness_chart(all_data)
            timeline = self.generate_timeline(opportunity_data, datetime.now())
            process_flow = self.generate_process_flow()
            activity_chart = self.generate_activity_chart(relationships_data)
            
            # Build report content
            report = self._build_report_content(
                all_data, relationship_diagram, completeness_chart, 
                timeline, process_flow, activity_chart
            )
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            
            return True
            
        except Exception as e:
            print(f"❌ Error generating report: {str(e)}")
            return False
    
    def _build_report_content(self, all_data: Dict, relationship_diagram: str,
                             completeness_chart: str, timeline: str,
                             process_flow: str, activity_chart: str) -> str:
        """Build the complete report content"""
        
        # Extract key data
        opportunity_data = all_data.get("opportunity", {})
        contacts_data = all_data.get("contacts", {})
        documents_data = all_data.get("documents", {})
        transcripts_data = all_data.get("transcripts", {})
        relationships_data = all_data.get("relationships", {})
        extraction_stats = all_data.get("extraction_stats", {})
        
        opp = opportunity_data.get("opportunity", {})
        account = opportunity_data.get("account", {})
        
        # Calculate processing time
        start_time = extraction_stats.get("start_time", datetime.now().isoformat())
        duration = (datetime.now() - datetime.fromisoformat(start_time)).total_seconds()
        
        report = f"""# Salesforce Opportunity Data Extraction Report

## 📊 Executive Summary

**Opportunity:** {opp.get('Name', 'Unknown')}  
**ID:** {opp.get('Id', 'Unknown')}  
**Account:** {account.get('Name', 'Unknown')}  
**Stage:** {opp.get('StageName', 'Unknown')}  
**Amount:** ${opp.get('Amount', 0):,.2f}  
**Close Date:** {opp.get('CloseDate', 'Unknown')}  

**Extraction Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Processing Time:** {duration:.2f} seconds  

## 🗂️ Data Extraction Metrics

| Category | Count | Status |
|----------|-------|--------|
| Contacts | {len(contacts_data.get('contacts', []))} | {'✅ Extracted' if contacts_data.get('contacts') else '⚠️ None found'} |
| Contact Roles | {len(contacts_data.get('contact_roles', []))} | {'✅ Extracted' if contacts_data.get('contact_roles') else '⚠️ None found'} |
| Documents | {stats.get("successful", 0) + stats.get("skipped", 0) + stats.get("failed", 0) if (stats := documents_data.get('stats', {})) else 0} | {documents_data.get('stats', {}).get('successful', 0)} Downloaded |
| Transcripts | {transcripts_data.get('stats', {}).get('transcripts_extracted', 0)} | ✅ Extracted |
| Tasks | {len(relationships_data.get('hierarchy', {}).get('direct_children', {}).get('opportunity', {}).get('tasks', []))} | ✅ Mapped |
| Events | {len(relationships_data.get('hierarchy', {}).get('direct_children', {}).get('opportunity', {}).get('events', []))} | ✅ Mapped |
| Cases | {len(relationships_data.get('hierarchy', {}).get('direct_children', {}).get('account', {}).get('cases', []))} | ✅ Mapped |

## 🔗 Object Relationships

{relationship_diagram}

## 📈 Data Completeness

{completeness_chart}

## 🔄 Extraction Process Flow

{process_flow}

## 📅 Timeline

{timeline}

{activity_chart}

## 👥 Key Contacts

| Name | Title | Email | Phone | Role |
|------|-------|-------|-------|------|
"""
        
        # Add contacts table
        contacts = contacts_data.get("contacts", [])[:10]  # Limit to 10
        contact_roles = contacts_data.get("contact_roles", [])
        
        if not contacts:
            report += "| No contacts found | N/A | N/A | N/A | N/A |\n"
        
        for contact in contacts:
            name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip()
            title = contact.get('Title', 'N/A')
            email = contact.get('Email', 'N/A')
            phone = contact.get('Phone', 'N/A')
            
            # Find role information
            role = "Contact"
            for cr in contact_roles:
                if cr.get("ContactId") == contact.get("Id"):
                    if cr.get("IsPrimary"):
                        role = f"**Primary - {cr.get('Role', 'Contact')}**"
                    else:
                        role = cr.get('Role', 'Contact')
                    break
            
            report += f"| {name} | {title} | {email} | {phone} | {role} |\n"
        
        # Document inventory
        doc_inventory = documents_data.get("inventory", {})
        doc_types = doc_inventory.get("by_type", {})
        
        report += f"""
## 📄 Document Inventory

### By Type
"""
        
        for doc_type, info in sorted(doc_types.items(), key=lambda x: x[0] or ""):
            count = info.get("count", 0)
            total_size = info.get("total_size", 0)
            size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
            
            report += f"\n**{doc_type.title()} ({count} files, {size_mb:.1f} MB total):**\n"
            
            files = info.get("files", [])[:5]  # Show first 5 files
            for file_info in files:
                file_size_mb = file_info.get("size", 0) / (1024 * 1024)
                report += f"- {file_info.get('title', 'Unknown')} ({file_size_mb:.2f} MB)\n"
        
        # Call transcripts
        transcript_stats = transcripts_data.get("stats", {})
        transcripts_extracted = transcript_stats.get("transcripts_extracted", 0)
        
        if transcripts_extracted > 0:
            report += f"""
## 📞 Call Transcripts

**Total Transcripts:** {transcripts_extracted}  
**Voice Calls Found:** {transcript_stats.get("voice_calls_found", 0)}  
**Messaging Sessions:** {transcript_stats.get("messaging_sessions_found", 0)}  
**Transcripts Cleaned:** {transcript_stats.get("transcripts_cleaned", 0)}  
"""
        
        # Recent activity
        analysis = relationships_data.get("analysis", {})
        activity_patterns = analysis.get("activity_patterns", {})
        recent_activity = activity_patterns.get("recent_activity", [])
        
        if recent_activity:
            report += """
## 📌 Recent Activity

### Last 10 Activities
| Type | Subject | Date | Owner |
|------|---------|------|-------|
"""
            for activity in recent_activity[:10]:
                activity_type = activity.get("type", "").title()
                subject = (activity.get("subject", "N/A")[:50] + "...") if len(activity.get("subject", "")) > 50 else activity.get("subject", "N/A")
                date = activity.get("date", "N/A")
                owner = activity.get("owner", "N/A")
                report += f"| {activity_type} | {subject} | {date} | {owner} |\n"
        
        # Errors and issues
        all_errors = []
        for component in [extraction_stats.get("opportunity", {}), extraction_stats.get("contacts", {}), 
                         extraction_stats.get("documents", {}), extraction_stats.get("transcripts", {}),
                         extraction_stats.get("relationships", {})]:
            errors = component.get("errors", [])
            all_errors.extend(errors)
        
        if all_errors:
            report += f"""
## ⚠️ Extraction Issues

The following issues were encountered during extraction:

"""
            for error in all_errors[:10]:  # Show first 10 errors
                report += f"- {error}\n"
        
        # Next steps
        output_dir = all_data.get("output_directory", "data/[opportunity_id]")
        
        report += f"""
## 🎯 Next Steps for LLM Analysis

1. **Transcript Analysis**
   - Process cleaned transcripts in `{output_dir}/transcripts/cleaned/`
   - Extract customer requirements and specifications
   - Identify key decision points and commitments

2. **Document Review**
   - Analyze quotes for pricing and service details
   - Review contracts for terms and conditions
   - Extract technical specifications from spreadsheets

3. **Contact Mapping**
   - Identify decision makers and technical contacts
   - Map organizational hierarchy
   - Determine communication preferences

4. **Provisioning Data Extraction**
   - Use the 80-attribute template from `provs/broadvoice_attributes_requirements.csv`
   - Apply 4-pass extraction methodology
   - Generate provisioning CSV with confidence scores

5. **Validation**
   - Cross-reference data across multiple sources
   - Flag missing critical information
   - Prepare follow-up questions for sales team

## 📁 Output Directory Structure

```
{output_dir}/
├── metadata.json           # Complete extraction metadata
├── opportunity.json        # Opportunity details
├── account.json           # Account information
├── contacts.json          # All contacts
├── summary.md             # This report
├── documents/
│   ├── quotes/           # Quote documents
│   ├── contracts/        # Contract documents  
│   ├── emails/           # Email exports
│   ├── spreadsheets/     # Excel/CSV files
│   ├── pdfs/            # PDF documents
│   └── other/           # Other file types
└── transcripts/
    ├── raw/             # Original transcripts
    └── cleaned/         # Processed transcripts
```

## 🔍 Data Quality Assessment

**Overall Data Quality:** {"HIGH" if not all_errors else "MEDIUM"}  
**Total Queries Executed:** {sum(comp.get("queries_executed", 0) for comp in [extraction_stats.get("opportunity", {}), extraction_stats.get("contacts", {}), extraction_stats.get("documents", {}), extraction_stats.get("transcripts", {}), extraction_stats.get("relationships", {})])}  
**Documents Downloaded:** {documents_data.get('stats', {}).get('successful', 0)} of {stats.get("successful", 0) + stats.get("skipped", 0) + stats.get("failed", 0) if (stats := documents_data.get('stats', {})) else 0}  
**Transcripts Extracted:** {transcripts_extracted}  
**Total Errors:** {len(all_errors)}  

---

*Generated by Salesforce Opportunity Extractor*  
*Processing completed at {datetime.now().isoformat()}*
"""
        
        return report
    
    def _clean_name_for_mermaid(self, name: str) -> str:
        """Clean name for safe use in Mermaid diagrams"""
        if not name:
            return "Unknown"
        
        # Replace problematic characters
        clean_name = name.replace('"', "'").replace("[", "(").replace("]", ")")
        clean_name = clean_name.replace("{", "(").replace("}", ")")
        
        # Limit length for readability
        if len(clean_name) > 30:
            clean_name = clean_name[:27] + "..."
        
        return clean_name
    
    def export_data_json(self, all_data: Dict, output_path: Path) -> bool:
        """
        Export all data as JSON file
        
        Args:
            all_data: All extracted data
            output_path: Path to save JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2, default=str, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Error exporting JSON: {str(e)}")
            return False