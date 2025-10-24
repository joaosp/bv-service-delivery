"""
Contact Data Extractor

Handles extraction of contact data and opportunity contact roles from Salesforce.
"""

from typing import Dict, List, Optional
from .base import SalesforceBase


class ContactExtractor(SalesforceBase):
    """Extracts contact data and relationships from Salesforce"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        super().__init__(org_username)
        self.contacts_data = []
        self.contact_roles_data = []
    
    def get_account_contacts(self, account_id: str) -> List[Dict]:
        """
        Get all contacts associated with an account
        
        Args:
            account_id: Salesforce account ID
            
        Returns:
            List of contact records
        """
        self.log_info(f"Fetching contacts for account: {account_id}")
        
        query = f"""
        SELECT Id, FirstName, LastName, Name, Email, Phone, MobilePhone,
               Title, Department, ReportsToId, ReportsTo.Name,
               MailingStreet, MailingCity, MailingState, MailingPostalCode,
               MailingCountry, Description, LeadSource, 
               CreatedDate, LastModifiedDate, LastActivityDate,
               DoNotCall, HasOptedOutOfEmail, EmailBouncedReason
        FROM Contact 
        WHERE AccountId = '{account_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.contacts_data = result["records"]
            self.log_success(f"Found {len(self.contacts_data)} contacts")
            return self.contacts_data
        
        self.log_info("No contacts found for account")
        return []
    
    def get_opportunity_contact_roles(self, opp_id: str) -> List[Dict]:
        """
        Get opportunity contact roles
        
        Args:
            opp_id: Salesforce opportunity ID
            
        Returns:
            List of opportunity contact role records
        """
        self.log_info("Fetching opportunity contact roles")
        
        query = f"""
        SELECT Id, ContactId, Contact.FirstName, Contact.LastName,
               Contact.Name, Contact.Email, Contact.Phone, Contact.Title,
               Contact.Department, Role, IsPrimary, CreatedDate
        FROM OpportunityContactRole
        WHERE OpportunityId = '{opp_id}'
        ORDER BY IsPrimary DESC, CreatedDate
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            self.contact_roles_data = result["records"]
            self.log_success(f"Found {len(self.contact_roles_data)} contact roles")
            return self.contact_roles_data
        
        self.log_info("No opportunity contact roles found")
        return []
    
    def get_contact_activities(self, contact_ids: List[str]) -> Dict[str, List[Dict]]:
        """
        Get activities (tasks and events) for contacts
        
        Args:
            contact_ids: List of contact IDs
            
        Returns:
            Dictionary mapping contact ID to list of activities
        """
        if not contact_ids:
            return {}
        
        self.log_info(f"Fetching activities for {len(contact_ids)} contacts")
        
        # Get tasks
        contact_ids_str = "', '".join(contact_ids)
        task_query = f"""
        SELECT Id, Subject, Status, Priority, ActivityDate, Description,
               WhoId, Who.Name, WhatId, What.Name, OwnerId, Owner.Name,
               CreatedDate, Type, CallType, CallDurationInSeconds
        FROM Task
        WHERE WhoId IN ('{contact_ids_str}')
        ORDER BY ActivityDate DESC
        LIMIT 100
        """
        
        tasks_result = self.run_soql_query(task_query)
        tasks = tasks_result["records"] if tasks_result else []
        
        # Get events
        event_query = f"""
        SELECT Id, Subject, StartDateTime, EndDateTime, Location,
               Description, WhoId, Who.Name, WhatId, What.Name,
               OwnerId, Owner.Name, CreatedDate, Type, DurationInMinutes
        FROM Event
        WHERE WhoId IN ('{contact_ids_str}')
        ORDER BY StartDateTime DESC
        LIMIT 100
        """
        
        events_result = self.run_soql_query(event_query)
        events = events_result["records"] if events_result else []
        
        # Group activities by contact
        activities_by_contact = {}
        
        for task in tasks:
            contact_id = task.get("WhoId")
            if contact_id not in activities_by_contact:
                activities_by_contact[contact_id] = []
            activities_by_contact[contact_id].append({
                "type": "task",
                "data": task
            })
        
        for event in events:
            contact_id = event.get("WhoId")
            if contact_id not in activities_by_contact:
                activities_by_contact[contact_id] = []
            activities_by_contact[contact_id].append({
                "type": "event", 
                "data": event
            })
        
        self.log_success(f"Found {len(tasks)} tasks and {len(events)} events")
        return activities_by_contact
    
    def get_contact_hierarchy(self, contacts: List[Dict] = None) -> Dict:
        """
        Build contact hierarchy based on ReportsTo relationships
        
        Args:
            contacts: List of contacts (if None, uses loaded contacts)
            
        Returns:
            Dictionary representing contact hierarchy
        """
        if not contacts:
            contacts = self.contacts_data
        
        if not contacts:
            return {}
        
        self.log_info("Building contact hierarchy")
        
        # Create lookup maps
        contacts_by_id = {contact["Id"]: contact for contact in contacts}
        hierarchy = {"managers": [], "individual_contributors": [], "unknown": []}
        
        for contact in contacts:
            reports_to_id = contact.get("ReportsToId")
            
            if reports_to_id and reports_to_id in contacts_by_id:
                # This person reports to someone in our list
                manager = contacts_by_id[reports_to_id]
                if "direct_reports" not in manager:
                    manager["direct_reports"] = []
                manager["direct_reports"].append(contact)
                
                # Add manager to managers list if not already there
                if manager not in hierarchy["managers"]:
                    hierarchy["managers"].append(manager)
            
            elif not reports_to_id:
                # No manager specified - could be top level
                hierarchy["individual_contributors"].append(contact)
            
            else:
                # Reports to someone not in our contact list
                hierarchy["unknown"].append(contact)
        
        # Remove managers from individual contributors
        manager_ids = {mgr["Id"] for mgr in hierarchy["managers"]}
        hierarchy["individual_contributors"] = [
            contact for contact in hierarchy["individual_contributors"]
            if contact["Id"] not in manager_ids
        ]
        
        self.log_success(f"Built hierarchy: {len(hierarchy['managers'])} managers, "
                        f"{len(hierarchy['individual_contributors'])} ICs, "
                        f"{len(hierarchy['unknown'])} unknown")
        
        return hierarchy
    
    def get_primary_contacts(self, contact_roles: List[Dict] = None) -> List[Dict]:
        """
        Get primary contacts from opportunity contact roles
        
        Args:
            contact_roles: List of contact roles (if None, uses instance data)
        
        Returns:
            List of primary contact records
        """
        roles_to_check = contact_roles if contact_roles is not None else self.contact_roles_data
        
        if not roles_to_check:
            return []
        
        primary_contacts = [
            role for role in roles_to_check 
            if role.get("IsPrimary")
        ]
        
        return primary_contacts
    
    def get_decision_makers(self, contacts: List[Dict] = None, contact_roles: List[Dict] = None) -> List[Dict]:
        """
        Identify potential decision makers based on titles and roles
        
        Args:
            contacts: List of contacts (if None, uses instance data)
            contact_roles: List of contact roles (if None, uses instance data)
        
        Returns:
            List of contacts likely to be decision makers
        """
        contacts_to_check = contacts if contacts is not None else self.contacts_data
        roles_to_check = contact_roles if contact_roles is not None else self.contact_roles_data
        
        decision_maker_keywords = [
            'ceo', 'cto', 'cfo', 'president', 'director', 'manager', 
            'head', 'vp', 'vice president', 'owner', 'principal',
            'decision maker', 'buyer'
        ]
        
        decision_makers = []
        
        # Check contact roles first
        if roles_to_check:
            for role in roles_to_check:
                role_name = role.get("Role") or ""
                role_name = role_name.lower() if role_name else ""
                if role_name and any(keyword in role_name for keyword in ['decision', 'buyer', 'approver']):
                    decision_makers.append(role)
        
        # Check contact titles
        if contacts_to_check:
            for contact in contacts_to_check:
                title = contact.get("Title") or ""
                title = title.lower() if title else ""
                if title and any(keyword in title for keyword in decision_maker_keywords):
                    # Add role info if available
                    contact_role = None
                    if roles_to_check:
                        contact_role = next(
                            (role for role in roles_to_check 
                             if role.get("ContactId") == contact["Id"]), 
                            None
                        )
                    decision_makers.append({
                        "contact": contact,
                        "role": contact_role
                    })
        
        self.log_info(f"Identified {len(decision_makers)} potential decision makers")
        return decision_makers
    
    def get_technical_contacts(self, contacts: List[Dict] = None, contact_roles: List[Dict] = None) -> List[Dict]:
        """
        Identify technical contacts based on titles and departments
        
        Args:
            contacts: List of contacts (if None, uses instance data)
            contact_roles: List of contact roles (if None, uses instance data)
        
        Returns:
            List of technical contacts
        """
        contacts_to_check = contacts if contacts is not None else self.contacts_data
        roles_to_check = contact_roles if contact_roles is not None else self.contact_roles_data
        
        technical_keywords = [
            'it', 'technical', 'engineer', 'developer', 'admin', 'administrator',
            'system', 'network', 'infrastructure', 'technology', 'architect'
        ]
        
        technical_contacts = []
        
        if contacts_to_check:
            for contact in contacts_to_check:
                title = contact.get("Title") or ""
                title = title.lower() if title else ""
                department = contact.get("Department") or ""
                department = department.lower() if department else ""
                
                if ((title and any(keyword in title for keyword in technical_keywords)) or
                    (department and any(keyword in department for keyword in technical_keywords))):
                    
                    # Add role info if available
                    contact_role = None
                    if roles_to_check:
                        contact_role = next(
                            (role for role in roles_to_check 
                             if role.get("ContactId") == contact["Id"]), 
                            None
                        )
                    technical_contacts.append({
                        "contact": contact,
                        "role": contact_role
                    })
        
        self.log_info(f"Identified {len(technical_contacts)} technical contacts")
        return technical_contacts
    
    def get_complete_contact_data(self, account_id: str, opp_id: str) -> Dict:
        """
        Get complete contact data including roles, activities, and analysis
        
        Args:
            account_id: Account ID
            opp_id: Opportunity ID
            
        Returns:
            Complete contact data dictionary
        """
        extraction_errors = []
        
        # Get base contact data
        contacts = self.get_account_contacts(account_id)
        contact_roles = self.get_opportunity_contact_roles(opp_id)
        
        # Get additional data with error handling
        contact_ids = [contact["Id"] for contact in contacts]
        
        activities = {}
        try:
            activities = self.get_contact_activities(contact_ids)
        except Exception as e:
            extraction_errors.append(f"Activities extraction failed: {str(e)}")
            self.log_warning(f"Failed to extract contact activities: {str(e)}")
        
        hierarchy = {}
        try:
            hierarchy = self.get_contact_hierarchy(contacts)
        except Exception as e:
            extraction_errors.append(f"Hierarchy extraction failed: {str(e)}")
            self.log_warning(f"Failed to extract contact hierarchy: {str(e)}")
        
        # Analysis with individual error handling
        primary_contacts = []
        try:
            primary_contacts = self.get_primary_contacts(contact_roles)
        except Exception as e:
            extraction_errors.append(f"Primary contacts analysis failed: {str(e)}")
            self.log_warning(f"Failed to analyze primary contacts: {str(e)}")
        
        decision_makers = []
        try:
            decision_makers = self.get_decision_makers(contacts, contact_roles)
        except Exception as e:
            extraction_errors.append(f"Decision makers analysis failed: {str(e)}")
            self.log_warning(f"Failed to analyze decision makers: {str(e)}")
        
        technical_contacts = []
        try:
            technical_contacts = self.get_technical_contacts(contacts, contact_roles)
        except Exception as e:
            extraction_errors.append(f"Technical contacts analysis failed: {str(e)}")
            self.log_warning(f"Failed to analyze technical contacts: {str(e)}")
        
        # Build result with error information
        result = {
            "contacts": contacts,
            "contact_roles": contact_roles,
            "activities": activities,
            "hierarchy": hierarchy,
            "analysis": {
                "primary_contacts": primary_contacts,
                "decision_makers": decision_makers,
                "technical_contacts": technical_contacts,
                "total_contacts": len(contacts),
                "contacts_with_roles": len(contact_roles)
            },
            "extraction_stats": self.get_extraction_stats()
        }
        
        # Add error information if any occurred
        if extraction_errors:
            result["partial_extraction_errors"] = extraction_errors
            self.log_warning(f"Contact extraction completed with {len(extraction_errors)} partial errors")
        
        return result
    
    def export_contacts_csv(self, output_path: str, contacts: List[Dict] = None):
        """
        Export contacts to CSV format
        
        Args:
            output_path: Path to save CSV file
            contacts: List of contacts (if None, uses loaded contacts)
        """
        import csv
        
        if not contacts:
            contacts = self.contacts_data
        
        if not contacts:
            self.log_warning("No contacts to export")
            return
        
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'Id', 'FirstName', 'LastName', 'Name', 'Email', 'Phone',
                    'Title', 'Department', 'ReportsTo', 'CreatedDate'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for contact in contacts:
                    row = {
                        'Id': contact.get('Id'),
                        'FirstName': contact.get('FirstName'),
                        'LastName': contact.get('LastName'),
                        'Name': contact.get('Name'),
                        'Email': contact.get('Email'),
                        'Phone': contact.get('Phone'),
                        'Title': contact.get('Title'),
                        'Department': contact.get('Department'),
                        'ReportsTo': contact.get('ReportsTo', {}).get('Name') if contact.get('ReportsTo') else '',
                        'CreatedDate': contact.get('CreatedDate')
                    }
                    writer.writerow(row)
            
            self.log_success(f"Exported {len(contacts)} contacts to {output_path}")
            
        except Exception as e:
            self.log_error(f"Failed to export contacts: {str(e)}")
    
    def get_current_contacts(self) -> List[Dict]:
        """Get currently loaded contacts"""
        return self.contacts_data
    
    def get_current_contact_roles(self) -> List[Dict]:
        """Get currently loaded contact roles"""
        return self.contact_roles_data