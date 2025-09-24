#!/usr/bin/env python3
"""
Salesforce Opportunity Data Extractor
Extracts all related data for a given Salesforce opportunity including:
- Related objects (Account, Contacts, Tasks, etc.)
- Attached documents (PDFs, Excel, emails, quotes)
- Call transcripts and recordings
"""

import json
import subprocess
import sys
import os
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import base64
import tempfile

class SalesforceOpportunityExtractor:
    """Extract comprehensive data from Salesforce opportunities"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        self.org = org_username
        self.data_dir = None
        self.opportunity_id = None
        self.opportunity_data = {}
        self.account_data = {}
        self.contacts_data = []
        self.documents_data = []
        self.transcripts_data = []
        self.relationships = {}
        self.extraction_stats = {
            "start_time": datetime.now().isoformat(),
            "queries_executed": 0,
            "documents_downloaded": 0,
            "transcripts_extracted": 0,
            "errors": []
        }
    
    def setup_directories(self, opp_id: str):
        """Create directory structure for opportunity data"""
        self.opportunity_id = opp_id
        self.data_dir = Path(f"data/{opp_id}")
        
        # Create main directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "documents").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "quotes").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "contracts").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "emails").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "spreadsheets").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "pdfs").mkdir(exist_ok=True)
        (self.data_dir / "documents" / "other").mkdir(exist_ok=True)
        (self.data_dir / "transcripts").mkdir(exist_ok=True)
        (self.data_dir / "transcripts" / "raw").mkdir(exist_ok=True)
        (self.data_dir / "transcripts" / "cleaned").mkdir(exist_ok=True)
        
        print(f"✅ Created directory structure at: {self.data_dir}")
    
    def run_soql_query(self, query: str, log_errors: bool = True) -> Optional[Dict]:
        """Execute SOQL query via SF CLI with improved error handling"""
        try:
            cmd = [
                "sf", "data", "query",
                "--target-org", self.org,
                "--query", query,
                "--json"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.extraction_stats["queries_executed"] += 1
            
            if result.returncode != 0:
                # Parse stderr for better error messages
                stderr_text = result.stderr.strip() if result.stderr else "Unknown error"
                stdout_text = result.stdout.strip() if result.stdout else ""
                
                # Try to extract meaningful error from JSON output
                error_detail = stderr_text
                if stdout_text:
                    try:
                        output_data = json.loads(stdout_text)
                        if "message" in output_data:
                            error_detail = output_data["message"]
                        elif "error" in output_data:
                            error_detail = str(output_data["error"])
                    except:
                        pass
                
                # Extract the object name from query for better context
                object_match = query.strip().split("FROM")[1].strip().split()[0] if "FROM" in query.upper() else "unknown object"
                
                error_msg = f"Query failed for {object_match}: {error_detail}"
                
                if log_errors:
                    self.extraction_stats["errors"].append(error_msg)
                    print(f"❌ {error_msg}")
                
                return None
            
            # Parse successful response
            data = json.loads(result.stdout)
            if "result" in data:
                return data["result"]
            return None
            
        except json.JSONDecodeError as e:
            error_msg = f"Query response parsing error: {str(e)}"
            if log_errors:
                self.extraction_stats["errors"].append(error_msg)
                print(f"❌ {error_msg}")
            return None
        except Exception as e:
            error_msg = f"Query exception: {str(e)}"
            if log_errors:
                self.extraction_stats["errors"].append(error_msg)
                print(f"❌ {error_msg}")
            return None
    
    def get_opportunity_by_id(self, opp_id: str) -> bool:
        """Fetch opportunity details by ID"""
        print(f"\n🔍 Fetching opportunity: {opp_id}")
        
        query = f"""
        SELECT Id, Name, AccountId, Account.Name, StageName, Amount, 
               CloseDate, Type, Description, NextStep, Probability,
               LeadSource, CampaignId, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate, IsClosed, IsWon,
               ForecastCategory, ForecastCategoryName
        FROM Opportunity 
        WHERE Id = '{opp_id}'
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.opportunity_data = result["records"][0]
            print(f"✅ Found opportunity: {self.opportunity_data.get('Name')}")
            return True
        return False
    
    def get_opportunity_by_name(self, opp_name: str) -> bool:
        """Fetch opportunity details by name"""
        print(f"\n🔍 Searching for opportunity: {opp_name}")
        
        query = f"""
        SELECT Id, Name, AccountId, Account.Name, StageName, Amount,
               CloseDate, Type, Description, NextStep, Probability,
               LeadSource, CampaignId, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate, IsClosed, IsWon,
               ForecastCategory, ForecastCategoryName
        FROM Opportunity 
        WHERE Name LIKE '%{opp_name}%'
        ORDER BY CreatedDate DESC
        LIMIT 5
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            if result["totalSize"] == 1:
                self.opportunity_data = result["records"][0]
                print(f"✅ Found opportunity: {self.opportunity_data.get('Name')}")
                return True
            else:
                print("\n⚠️  Multiple opportunities found:")
                for i, opp in enumerate(result["records"], 1):
                    print(f"  {i}. {opp['Name']} (ID: {opp['Id']}) - Stage: {opp['StageName']}")
                print("\nPlease run with specific opportunity ID")
                return False
        return False
    
    def get_account_details(self):
        """Fetch related account information"""
        if not self.opportunity_data.get("AccountId"):
            return
        
        account_id = self.opportunity_data["AccountId"]
        print(f"\n🔍 Fetching account details for: {account_id}")
        
        query = f"""
        SELECT Id, Name, Type, Industry, AnnualRevenue, NumberOfEmployees,
               BillingStreet, BillingCity, BillingState, BillingPostalCode,
               BillingCountry, ShippingStreet, ShippingCity, ShippingState,
               ShippingPostalCode, Phone, Fax, Website, Description,
               ParentId, Parent.Name, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate
        FROM Account 
        WHERE Id = '{account_id}'
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.account_data = result["records"][0]
            print(f"✅ Found account: {self.account_data.get('Name')}")
    
    def get_related_contacts(self):
        """Fetch all contacts related to the account"""
        if not self.opportunity_data.get("AccountId"):
            return
        
        account_id = self.opportunity_data["AccountId"]
        print(f"\n🔍 Fetching contacts for account")
        
        # Get contacts directly related to account
        query = f"""
        SELECT Id, FirstName, LastName, Email, Phone, MobilePhone,
               Title, Department, ReportsToId, ReportsTo.Name,
               MailingStreet, MailingCity, MailingState, MailingPostalCode,
               Description, LeadSource, CreatedDate, LastModifiedDate
        FROM Contact 
        WHERE AccountId = '{account_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.contacts_data = result["records"]
            print(f"✅ Found {len(self.contacts_data)} contacts")
            
        # Also get OpportunityContactRoles
        print(f"\n🔍 Fetching opportunity contact roles")
        query = f"""
        SELECT Id, ContactId, Contact.FirstName, Contact.LastName,
               Contact.Email, Contact.Phone, Contact.Title,
               Role, IsPrimary
        FROM OpportunityContactRole
        WHERE OpportunityId = '{self.opportunity_id}'
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            print(f"✅ Found {result['totalSize']} contact roles")
            self.relationships["contact_roles"] = result["records"]
    
    def get_related_objects(self):
        """Map all related objects"""
        print(f"\n🔍 Mapping all related objects")
        
        # Get Tasks
        query = f"""
        SELECT Id, Subject, Status, Priority, ActivityDate,
               Description, WhoId, Who.Name, WhatId, What.Name,
               OwnerId, Owner.Name, CreatedDate
        FROM Task
        WHERE WhatId = '{self.opportunity_id}'
        ORDER BY CreatedDate DESC
        """
        result = self.run_soql_query(query)
        if result:
            self.relationships["tasks"] = result["records"]
            print(f"✅ Found {result['totalSize']} tasks")
        
        # Get Events
        query = f"""
        SELECT Id, Subject, StartDateTime, EndDateTime, Location,
               Description, WhoId, Who.Name, WhatId, What.Name,
               OwnerId, Owner.Name, CreatedDate
        FROM Event
        WHERE WhatId = '{self.opportunity_id}'
        ORDER BY StartDateTime DESC
        """
        result = self.run_soql_query(query)
        if result:
            self.relationships["events"] = result["records"]
            print(f"✅ Found {result['totalSize']} events")
        
        # Get Cases (if any)
        if self.account_data.get("Id"):
            query = f"""
            SELECT Id, CaseNumber, Subject, Status, Priority,
                   Description, Type, CreatedDate
            FROM Case
            WHERE AccountId = '{self.account_data["Id"]}'
            ORDER BY CreatedDate DESC
            LIMIT 20
            """
            result = self.run_soql_query(query)
            if result:
                self.relationships["cases"] = result["records"]
                print(f"✅ Found {result['totalSize']} cases")
        
        # Get Notes
        query = f"""
        SELECT Id, Title, Body, CreatedDate, LastModifiedDate,
               CreatedBy.Name
        FROM Note
        WHERE ParentId = '{self.opportunity_id}'
        ORDER BY CreatedDate DESC
        """
        result = self.run_soql_query(query)
        if result:
            self.relationships["notes"] = result["records"]
            print(f"✅ Found {result['totalSize']} notes")
    
    def get_document_list(self):
        """Get list of all documents attached to opportunity"""
        print(f"\n📄 Fetching document list")
        
        # Get ContentDocumentLinks
        query = f"""
        SELECT Id, ContentDocumentId, ContentDocument.Title,
               ContentDocument.FileType, ContentDocument.FileExtension,
               ContentDocument.ContentSize, ContentDocument.CreatedDate,
               ContentDocument.LatestPublishedVersionId
        FROM ContentDocumentLink
        WHERE LinkedEntityId = '{self.opportunity_id}'
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.documents_data = result["records"]
            print(f"✅ Found {len(self.documents_data)} documents")
            
            # Categorize documents
            doc_types = {}
            for doc in self.documents_data:
                ext = doc.get("ContentDocument", {}).get("FileExtension", "unknown").lower()
                doc_types[ext] = doc_types.get(ext, 0) + 1
            
            print("📊 Document types:")
            for ext, count in sorted(doc_types.items()):
                print(f"   - {ext}: {count} file(s)")
    
    def download_document(self, doc_info: Dict) -> bool:
        """Download a single document from Salesforce"""
        try:
            doc = doc_info.get("ContentDocument", {})
            version_id = doc.get("LatestPublishedVersionId")
            title = doc.get("Title", "untitled")
            extension = doc.get("FileExtension", "bin").lower()
            
            if not version_id:
                return False
            
            # Determine target folder
            if extension == "pdf":
                if "quote" in title.lower():
                    folder = "quotes"
                elif "loa" in title.lower() or "letter" in title.lower():
                    folder = "contracts"
                else:
                    folder = "pdfs"
            elif extension in ["xlsx", "xls", "csv"]:
                folder = "spreadsheets"
            elif extension in ["docx", "doc"]:
                if "contract" in title.lower():
                    folder = "contracts"
                else:
                    folder = "other"
            elif extension in ["msg", "eml"]:
                folder = "emails"
            elif extension in ["png", "jpg", "jpeg", "gif", "bmp"]:
                folder = "other"
            else:
                folder = "other"
            
            # Clean filename
            safe_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', title)[:100]
            filename = f"{safe_title}.{extension}"
            filepath = self.data_dir / "documents" / folder / filename
            
            # Skip if file already exists
            if filepath.exists():
                print(f"   ✓ Already downloaded: {filename}")
                self.extraction_stats["documents_downloaded"] += 1
                return True
            
            print(f"   ⬇️  Downloading: {filename}")
            
            # Method 1: Use REST API directly
            api_endpoint = f"services/data/v64.0/sobjects/ContentVersion/{version_id}/VersionData"
            
            cmd = [
                "sf", "api", "request", "rest",
                api_endpoint,
                "--method", "GET",
                "--target-org", self.org
            ]
            
            result = subprocess.run(cmd, capture_output=True, check=False)
            
            if result.returncode == 0 and result.stdout:
                # Save binary data directly
                with open(filepath, 'wb') as f:
                    f.write(result.stdout)
                self.extraction_stats["documents_downloaded"] += 1
                print(f"   ✅ Downloaded: {filename}")
                return True
            
            # Method 2: Try using sfdx force:source:retrieve
            print(f"   ⚠️  Trying alternative method for: {filename}")
            
            # Create temp directory
            temp_dir = self.data_dir / "documents" / "temp"
            temp_dir.mkdir(exist_ok=True)
            
            cmd = [
                "sf", "data", "export", "files",
                "--source-dir", "ContentVersion",
                "--content-type", "VersionData",
                "--ids", version_id,
                "--output-dir", str(temp_dir),
                "--target-org", self.org
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            # Check if file was downloaded to temp
            for temp_file in temp_dir.glob("*"):
                if version_id in str(temp_file):
                    # Move to correct location
                    temp_file.rename(filepath)
                    self.extraction_stats["documents_downloaded"] += 1
                    print(f"   ✅ Downloaded: {filename}")
                    return True
            
            # Method 3: Manual REST API call with curl
            print(f"   ⚠️  Trying curl method for: {filename}")
            
            # First get the session info
            cmd = ["sf", "org", "display", "--target-org", self.org, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                org_info = json.loads(result.stdout)
                if org_info.get("result"):
                    instance_url = org_info["result"].get("instanceUrl")
                    access_token = org_info["result"].get("accessToken")
                    
                    if instance_url and access_token:
                        curl_cmd = [
                            "curl",
                            "-H", f"Authorization: Bearer {access_token}",
                            "-o", str(filepath),
                            f"{instance_url}{api_endpoint}"
                        ]
                        
                        result = subprocess.run(curl_cmd, capture_output=True, check=False)
                        
                        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 0:
                            self.extraction_stats["documents_downloaded"] += 1
                            print(f"   ✅ Downloaded: {filename}")
                            return True
            
            print(f"   ❌ Could not download: {filename}")
            return False
            
        except Exception as e:
            error_msg = f"Download error for {title}: {str(e)}"
            self.extraction_stats["errors"].append(error_msg)
            print(f"   ❌ {error_msg}")
            return False
    
    def download_all_documents(self):
        """Download all documents attached to opportunity"""
        if not self.documents_data:
            print("\n📄 No documents to download")
            return
        
        print(f"\n📥 Downloading {len(self.documents_data)} documents...")
        
        for doc in self.documents_data:
            self.download_document(doc)
        
        print(f"✅ Downloaded {self.extraction_stats['documents_downloaded']} documents")
    
    def extract_call_transcripts(self):
        """Extract call transcripts from various sources"""
        print(f"\n📞 Extracting call transcripts")
        
        # Try multiple possible custom object names for call transcripts
        custom_objects = [
            ("CallAITranscript__c", "OpportunityId__c", "Transcript__c", "CallDate__c"),
            ("CallTranscript__c", "Opportunity__c", "Transcript__c", "Date__c"),
            ("Call_Transcript__c", "OpportunityId__c", "Body__c", "CallDate__c"),
            ("ConversationIntelligence__c", "RelatedTo__c", "TranscriptBody__c", "Date__c")
        ]
        
        for obj_name, opp_field, transcript_field, date_field in custom_objects:
            print(f"   🔍 Trying {obj_name}...")
            query = f"""
            SELECT Id, Name, {transcript_field}, {date_field}, CreatedDate
            FROM {obj_name}
            WHERE {opp_field} = '{self.opportunity_id}'
            ORDER BY CreatedDate DESC
            """
            
            result = self.run_soql_query(query, log_errors=False)
            if result and result.get("totalSize", 0) > 0:
                print(f"✅ Found {result['totalSize']} transcripts in {obj_name}")
                for i, transcript in enumerate(result["records"], 1):
                    self.transcripts_data.append(transcript)
                    # Save transcript
                    if transcript.get(transcript_field):
                        date_value = transcript.get(date_field, transcript.get('CreatedDate', 'unknown'))
                        filename = f"transcript_{i}_{date_value[:10]}.txt"
                        filepath = self.data_dir / "transcripts" / "raw" / filename
                        with open(filepath, 'w') as f:
                            f.write(transcript[transcript_field])
                        self.extraction_stats["transcripts_extracted"] += 1
                break  # Found transcripts, no need to try other objects
        
        if not self.transcripts_data:
            print("   ℹ️  No custom transcript objects found with data")
        
        # Check for transcripts in Task descriptions
        if self.relationships.get("tasks"):
            for task in self.relationships["tasks"]:
                if task.get("Subject") and "call" in task["Subject"].lower():
                    if task.get("Description") and len(task["Description"]) > 500:
                        filename = f"task_transcript_{task['Id']}.txt"
                        filepath = self.data_dir / "transcripts" / "raw" / filename
                        with open(filepath, 'w') as f:
                            f.write(f"Task: {task['Subject']}\n")
                            f.write(f"Date: {task['ActivityDate']}\n")
                            f.write(f"---\n{task['Description']}")
                        self.extraction_stats["transcripts_extracted"] += 1
        
        # Check EmailMessage for conversation threads
        query = f"""
        SELECT Id, Subject, TextBody, HtmlBody, MessageDate,
               FromAddress, ToAddress, Status
        FROM EmailMessage
        WHERE RelatedToId = '{self.opportunity_id}'
        ORDER BY MessageDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            print(f"✅ Found {result['totalSize']} email messages")
            email_thread = []
            for email in result["records"]:
                email_thread.append({
                    "date": email.get("MessageDate"),
                    "from": email.get("FromAddress"),
                    "to": email.get("ToAddress"),
                    "subject": email.get("Subject"),
                    "body": email.get("TextBody") or email.get("HtmlBody", "")
                })
            
            if email_thread:
                filepath = self.data_dir / "transcripts" / "raw" / "email_thread.json"
                with open(filepath, 'w') as f:
                    json.dump(email_thread, f, indent=2)
        
        # Clean transcripts if cleanup script exists
        if os.path.exists("cleanup_transcript.py"):
            print("\n🧹 Cleaning transcripts...")
            raw_dir = self.data_dir / "transcripts" / "raw"
            cleaned_dir = self.data_dir / "transcripts" / "cleaned"
            
            for raw_file in raw_dir.glob("*.txt"):
                if "callai" in raw_file.name or "task" in raw_file.name:
                    cleaned_name = raw_file.stem + "_cleaned.txt"
                    cleaned_path = cleaned_dir / cleaned_name
                    
                    cmd = ["python", "cleanup_transcript.py", str(raw_file), str(cleaned_path)]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    
                    if result.returncode == 0:
                        print(f"   ✅ Cleaned: {raw_file.name}")
                    else:
                        print(f"   ⚠️  Could not clean: {raw_file.name}")
        
        print(f"✅ Extracted {self.extraction_stats['transcripts_extracted']} transcripts")
    
    def generate_mermaid_diagrams(self) -> Dict[str, str]:
        """Generate Mermaid diagrams for relationships"""
        diagrams = {}
        
        # Object Relationship Diagram
        relationship_lines = []
        
        # Account to Opportunity
        if self.account_data:
            account_name = self.account_data.get("Name", "Account").replace('"', "'")
            opp_name = self.opportunity_data.get("Name", "Opportunity").replace('"', "'")
            relationship_lines.append(f'    Account["{account_name}"] --> Opp["{opp_name}"]')
        
        # Contacts
        for i, contact in enumerate(self.contacts_data[:5], 1):  # Limit to 5 for readability
            contact_name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}"
            contact_title = contact.get("Title", "Contact")
            relationship_lines.append(f'    Opp --> Contact{i}["{contact_name}<br/>{contact_title}"]')
        
        # Documents
        doc_counts = {}
        for doc in self.documents_data:
            ext = doc.get("ContentDocument", {}).get("FileExtension", "unknown").lower()
            doc_counts[ext] = doc_counts.get(ext, 0) + 1
        
        for ext, count in list(doc_counts.items())[:5]:  # Top 5 document types
            relationship_lines.append(f'    Opp --> Docs_{ext}["{count} {ext.upper()} files"]')
        
        # Tasks and Events
        if self.relationships.get("tasks"):
            relationship_lines.append(f'    Opp --> Tasks["{len(self.relationships["tasks"])} Tasks"]')
        
        if self.relationships.get("events"):
            relationship_lines.append(f'    Opp --> Events["{len(self.relationships["events"])} Events"]')
        
        if self.extraction_stats["transcripts_extracted"] > 0:
            relationship_lines.append(f'    Opp --> Transcripts["{self.extraction_stats["transcripts_extracted"]} Transcripts"]')
        
        diagrams["relationships"] = f"""```mermaid
graph TD
{chr(10).join(relationship_lines)}
    
    style Account fill:#e1f5fe
    style Opp fill:#fff3e0
    style Tasks fill:#f3e5f5
    style Events fill:#f3e5f5
    style Transcripts fill:#e8f5e9
```"""
        
        # Data Completeness Pie Chart
        total_items = (
            len(self.contacts_data) +
            len(self.documents_data) +
            self.extraction_stats["transcripts_extracted"] +
            len(self.relationships.get("tasks", [])) +
            len(self.relationships.get("events", []))
        )
        
        if total_items > 0:
            diagrams["completeness"] = f"""```mermaid
pie title Data Extraction Overview
    "Contacts" : {len(self.contacts_data)}
    "Documents" : {len(self.documents_data)}
    "Transcripts" : {self.extraction_stats["transcripts_extracted"]}
    "Tasks" : {len(self.relationships.get("tasks", []))}
    "Events" : {len(self.relationships.get("events", []))}
```"""
        
        # Process Flow
        diagrams["process"] = """```mermaid
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
        
        # Timeline (if we have dates)
        if self.opportunity_data.get("CreatedDate"):
            created = self.opportunity_data["CreatedDate"][:10]
            today = datetime.now().strftime("%Y-%m-%d")
            
            diagrams["timeline"] = f"""```mermaid
gantt
    title Opportunity Timeline
    dateFormat YYYY-MM-DD
    section Lifecycle
    Opportunity Created    :done, opp1, {created}, 1d
    Data Extraction       :active, extract, {today}, 1d
    section Analysis
    LLM Processing        :planned, after extract, 2d
    Provisioning Creation :planned, after extract, 3d
```"""
        
        return diagrams
    
    def generate_summary_report(self):
        """Generate comprehensive markdown report with Mermaid visualizations"""
        print(f"\n📝 Generating summary report")
        
        diagrams = self.generate_mermaid_diagrams()
        
        # Calculate metrics
        end_time = datetime.now()
        start_time = datetime.fromisoformat(self.extraction_stats["start_time"])
        duration = (end_time - start_time).total_seconds()
        
        report = f"""# Salesforce Opportunity Data Extraction Report

## 📊 Executive Summary

**Opportunity:** {self.opportunity_data.get('Name', 'Unknown')}  
**ID:** {self.opportunity_id}  
**Account:** {self.account_data.get('Name', 'Unknown')}  
**Stage:** {self.opportunity_data.get('StageName', 'Unknown')}  
**Amount:** ${self.opportunity_data.get('Amount', 0):,.2f}  
**Close Date:** {self.opportunity_data.get('CloseDate', 'Unknown')}  

**Extraction Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Processing Time:** {duration:.2f} seconds  

## 🗂️ Data Extraction Metrics

| Category | Count | Status |
|----------|-------|--------|
| Contacts | {len(self.contacts_data)} | ✅ Extracted |
| Documents | {len(self.documents_data)} | {self.extraction_stats['documents_downloaded']} Downloaded |
| Transcripts | {self.extraction_stats['transcripts_extracted']} | ✅ Extracted |
| Tasks | {len(self.relationships.get('tasks', []))} | ✅ Mapped |
| Events | {len(self.relationships.get('events', []))} | ✅ Mapped |
| Cases | {len(self.relationships.get('cases', []))} | ✅ Mapped |
| Notes | {len(self.relationships.get('notes', []))} | ✅ Mapped |

## 🔗 Object Relationships

{diagrams.get('relationships', '')}

## 📈 Data Completeness

{diagrams.get('completeness', '')}

## 🔄 Extraction Process Flow

{diagrams.get('process', '')}

## 📅 Timeline

{diagrams.get('timeline', '')}

## 👥 Key Contacts

| Name | Title | Email | Phone | Role |
|------|-------|-------|-------|------|
"""
        
        # Add contacts table
        for contact in self.contacts_data[:10]:  # Limit to 10
            name = f"{contact.get('FirstName', '')} {contact.get('LastName', '')}"
            title = contact.get('Title', 'N/A')
            email = contact.get('Email', 'N/A')
            phone = contact.get('Phone', 'N/A')
            
            # Check if primary contact
            role = "Contact"
            if self.relationships.get("contact_roles"):
                for cr in self.relationships["contact_roles"]:
                    if cr.get("ContactId") == contact.get("Id"):
                        if cr.get("IsPrimary"):
                            role = f"**Primary - {cr.get('Role', 'Contact')}**"
                        else:
                            role = cr.get('Role', 'Contact')
                        break
            
            report += f"| {name} | {title} | {email} | {phone} | {role} |\n"
        
        # Document inventory
        report += f"""
## 📄 Document Inventory

### By Type
"""
        doc_types = {}
        for doc in self.documents_data:
            ext = doc.get("ContentDocument", {}).get("FileExtension", "unknown").lower()
            title = doc.get("ContentDocument", {}).get("Title", "Untitled")
            size = doc.get("ContentDocument", {}).get("ContentSize", 0)
            
            if ext not in doc_types:
                doc_types[ext] = []
            doc_types[ext].append({
                "title": title,
                "size": size
            })
        
        for ext, docs in sorted(doc_types.items()):
            report += f"\n**{ext.upper()} Files ({len(docs)}):**\n"
            for doc in docs[:5]:  # Limit to 5 per type
                size_mb = doc['size'] / (1024 * 1024)
                report += f"- {doc['title']} ({size_mb:.2f} MB)\n"
        
        # Call Transcripts
        if self.extraction_stats["transcripts_extracted"] > 0:
            report += f"""
## 📞 Call Transcripts

**Total Transcripts:** {self.extraction_stats["transcripts_extracted"]}  
**Location:** `{self.data_dir}/transcripts/`  

### Available Transcripts:
"""
            raw_dir = self.data_dir / "transcripts" / "raw"
            for transcript_file in raw_dir.glob("*.txt"):
                report += f"- {transcript_file.name}\n"
        
        # Recent Activity
        report += """
## 📌 Recent Activity

### Last 5 Tasks
| Subject | Status | Date | Owner |
|---------|--------|------|-------|
"""
        tasks = self.relationships.get("tasks", [])[:5]
        for task in tasks:
            subject = task.get("Subject", "N/A")[:50]
            status = task.get("Status", "N/A")
            date = task.get("ActivityDate", "N/A")
            owner = task.get("Owner", {}).get("Name", "N/A") if task.get("Owner") else "N/A"
            report += f"| {subject} | {status} | {date} | {owner} |\n"
        
        # Errors and Issues
        if self.extraction_stats["errors"]:
            report += f"""
## ⚠️ Extraction Issues

The following issues were encountered during extraction:

"""
            for error in self.extraction_stats["errors"]:
                report += f"- {error}\n"
        
        # Next Steps
        report += f"""
## 🎯 Next Steps for LLM Analysis

1. **Transcript Analysis**
   - Process cleaned transcripts in `{self.data_dir}/transcripts/cleaned/`
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
{self.data_dir}/
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

**Overall Data Quality:** {"HIGH" if self.extraction_stats["errors"] == [] else "MEDIUM"}  
**Queries Executed:** {self.extraction_stats["queries_executed"]}  
**Documents Downloaded:** {self.extraction_stats["documents_downloaded"]} of {len(self.documents_data)}  
**Transcripts Extracted:** {self.extraction_stats["transcripts_extracted"]}  
**Errors Encountered:** {len(self.extraction_stats["errors"])}  

---

*Generated by Salesforce Opportunity Extractor*  
*Processing completed at {datetime.now().isoformat()}*
"""
        
        # Save report
        report_path = self.data_dir / "summary.md"
        with open(report_path, 'w') as f:
            f.write(report)
        
        print(f"✅ Summary report saved to: {report_path}")
    
    def save_metadata(self):
        """Save all extracted data as JSON files"""
        print(f"\n💾 Saving metadata files")
        
        # Save opportunity data
        with open(self.data_dir / "opportunity.json", 'w') as f:
            json.dump(self.opportunity_data, f, indent=2, default=str)
        
        # Save account data
        if self.account_data:
            with open(self.data_dir / "account.json", 'w') as f:
                json.dump(self.account_data, f, indent=2, default=str)
        
        # Save contacts
        if self.contacts_data:
            with open(self.data_dir / "contacts.json", 'w') as f:
                json.dump(self.contacts_data, f, indent=2, default=str)
        
        # Save complete metadata
        metadata = {
            "extraction_stats": self.extraction_stats,
            "opportunity": self.opportunity_data,
            "account": self.account_data,
            "contacts": self.contacts_data,
            "documents": self.documents_data,
            "relationships": self.relationships,
            "transcripts_count": self.extraction_stats["transcripts_extracted"]
        }
        
        with open(self.data_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        print("✅ Metadata files saved")
    
    def extract_opportunity_data(self, opp_id: str = None, opp_name: str = None):
        """Main extraction workflow"""
        print("=" * 60)
        print("🚀 SALESFORCE OPPORTUNITY DATA EXTRACTOR")
        print("=" * 60)
        
        # Find opportunity
        if opp_id:
            if not self.get_opportunity_by_id(opp_id):
                print("❌ Opportunity not found")
                return False
        elif opp_name:
            if not self.get_opportunity_by_name(opp_name):
                print("❌ Opportunity not found or multiple matches")
                return False
        else:
            print("❌ No opportunity ID or name provided")
            return False
        
        # Setup directories
        self.setup_directories(self.opportunity_data["Id"])
        
        # Extract all data
        self.get_account_details()
        self.get_related_contacts()
        self.get_related_objects()
        self.get_document_list()
        self.download_all_documents()
        self.extract_call_transcripts()
        
        # Generate outputs
        self.save_metadata()
        self.generate_summary_report()
        
        print("\n" + "=" * 60)
        print("✅ EXTRACTION COMPLETE!")
        print(f"📁 Data saved to: {self.data_dir}")
        print(f"📊 View summary: {self.data_dir}/summary.md")
        print("=" * 60)
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Extract all data related to a Salesforce opportunity"
    )
    parser.add_argument(
        "--opp-id",
        help="Opportunity ID (18-character Salesforce ID)"
    )
    parser.add_argument(
        "--opp-name",
        help="Opportunity name (will search for matches)"
    )
    parser.add_argument(
        "--org",
        default="jcamarate@broadvoice.com",
        help="Salesforce org username (default: jcamarate@broadvoice.com)"
    )
    
    args = parser.parse_args()
    
    if not args.opp_id and not args.opp_name:
        print("❌ Error: Please provide either --opp-id or --opp-name")
        parser.print_help()
        sys.exit(1)
    
    # Create extractor and run
    extractor = SalesforceOpportunityExtractor(org_username=args.org)
    success = extractor.extract_opportunity_data(
        opp_id=args.opp_id,
        opp_name=args.opp_name
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()