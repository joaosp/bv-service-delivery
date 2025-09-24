"""
Relationship Mapper

Handles mapping of all related objects and activities for opportunities and accounts.
Provides comprehensive relationship discovery and analysis.
"""

from typing import Dict, List, Optional, Set, Tuple
from .base import SalesforceBase


class RelationshipMapper(SalesforceBase):
    """Maps and analyzes relationships between Salesforce objects"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        super().__init__(org_username)
        self.relationships = {}
        self.relationship_stats = {
            "total_objects": 0,
            "total_relationships": 0,
            "object_counts": {}
        }
    
    def get_tasks(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get all tasks related to an entity
        
        Args:
            entity_id: Entity ID (Opportunity, Account, etc.)
            entity_type: Type of entity for logging
            
        Returns:
            List of Task records
        """
        self.log_info(f"Fetching tasks for {entity_type}")
        
        query = f"""
        SELECT Id, Subject, Status, Priority, ActivityDate, Description,
               WhoId, Who.Name, WhatId, What.Name, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate, Type, CallType,
               CallDurationInSeconds, IsRecurrence
        FROM Task
        WHERE WhatId = '{entity_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            tasks = result["records"]
            self.log_success(f"Found {len(tasks)} tasks")
            self.relationship_stats["object_counts"]["tasks"] = len(tasks)
            return tasks
        
        self.log_info("No tasks found")
        return []
    
    def get_events(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get all events related to an entity
        
        Args:
            entity_id: Entity ID
            entity_type: Type of entity for logging
            
        Returns:
            List of Event records
        """
        self.log_info(f"Fetching events for {entity_type}")
        
        query = f"""
        SELECT Id, Subject, StartDateTime, EndDateTime, Location, Description,
               WhoId, Who.Name, WhatId, What.Name, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate, Type, DurationInMinutes,
               IsRecurrence, IsAllDayEvent
        FROM Event
        WHERE WhatId = '{entity_id}'
        ORDER BY StartDateTime DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            events = result["records"]
            self.log_success(f"Found {len(events)} events")
            self.relationship_stats["object_counts"]["events"] = len(events)
            return events
        
        self.log_info("No events found")
        return []
    
    def get_cases(self, account_id: str) -> List[Dict]:
        """
        Get all cases for an account
        
        Args:
            account_id: Account ID
            
        Returns:
            List of Case records
        """
        self.log_info("Fetching cases for account")
        
        query = f"""
        SELECT Id, CaseNumber, Subject, Status, Priority, Type, Reason,
               Description, CreatedDate, LastModifiedDate, ClosedDate,
               OwnerId, Owner.Name, ContactId, Contact.Name,
               ParentId, Parent.CaseNumber, IsClosed, IsEscalated,
               Origin, SuppliedEmail, SuppliedPhone
        FROM Case
        WHERE AccountId = '{account_id}'
        ORDER BY CreatedDate DESC
        LIMIT 100
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            cases = result["records"]
            self.log_success(f"Found {len(cases)} cases")
            self.relationship_stats["object_counts"]["cases"] = len(cases)
            return cases
        
        self.log_info("No cases found")
        return []
    
    def get_notes(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get all notes for an entity
        
        Args:
            entity_id: Entity ID
            entity_type: Type of entity for logging
            
        Returns:
            List of Note records
        """
        self.log_info(f"Fetching notes for {entity_type}")
        
        query = f"""
        SELECT Id, Title, Body, CreatedDate, LastModifiedDate,
               CreatedBy.Name, LastModifiedBy.Name, IsPrivate
        FROM Note
        WHERE ParentId = '{entity_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            notes = result["records"]
            self.log_success(f"Found {len(notes)} notes")
            self.relationship_stats["object_counts"]["notes"] = len(notes)
            return notes
        
        self.log_info("No notes found")
        return []
    
    def get_email_messages(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get email messages related to an entity
        
        Args:
            entity_id: Entity ID
            entity_type: Type of entity for logging
            
        Returns:
            List of EmailMessage records
        """
        self.log_info(f"Fetching email messages for {entity_type}")
        
        query = f"""
        SELECT Id, Subject, TextBody, HtmlBody, MessageDate,
               FromAddress, ToAddress, CcAddress, BccAddress,
               Status, CreatedDate, LastModifiedDate,
               CreatedBy.Name, Incoming, HasAttachment
        FROM EmailMessage
        WHERE RelatedToId = '{entity_id}'
        ORDER BY MessageDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            emails = result["records"]
            self.log_success(f"Found {len(emails)} email messages")
            self.relationship_stats["object_counts"]["emails"] = len(emails)
            return emails
        
        self.log_info("No email messages found")
        return []
    
    def get_feed_items(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get Chatter feed items for an entity
        
        Args:
            entity_id: Entity ID
            entity_type: Type of entity for logging
            
        Returns:
            List of FeedItem records
        """
        self.log_info(f"Fetching feed items for {entity_type}")
        
        # Determine feed object type
        feed_object = "OpportunityFeed" if entity_type == "opportunity" else "AccountFeed"
        
        query = f"""
        SELECT Id, Type, CreatedDate, CreatedBy.Name, Body, Title,
               LinkUrl, CommentCount, LikeCount
        FROM {feed_object}
        WHERE ParentId = '{entity_id}'
        ORDER BY CreatedDate DESC
        LIMIT 50
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            feed_items = result["records"]
            self.log_success(f"Found {len(feed_items)} feed items")
            self.relationship_stats["object_counts"]["feed_items"] = len(feed_items)
            return feed_items
        
        self.log_info("No feed items found")
        return []
    
    def get_attachments(self, entity_id: str, entity_type: str = "opportunity") -> List[Dict]:
        """
        Get legacy attachments for an entity
        
        Args:
            entity_id: Entity ID
            entity_type: Type of entity for logging
            
        Returns:
            List of Attachment records
        """
        self.log_info(f"Fetching legacy attachments for {entity_type}")
        
        query = f"""
        SELECT Id, Name, ContentType, BodyLength, CreatedDate,
               CreatedBy.Name, Description, IsPrivate
        FROM Attachment
        WHERE ParentId = '{entity_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            attachments = result["records"]
            self.log_success(f"Found {len(attachments)} legacy attachments")
            self.relationship_stats["object_counts"]["attachments"] = len(attachments)
            return attachments
        
        self.log_info("No legacy attachments found")
        return []
    
    def get_related_opportunities(self, account_id: str, exclude_id: str = None) -> List[Dict]:
        """
        Get other opportunities for the same account
        
        Args:
            account_id: Account ID
            exclude_id: Opportunity ID to exclude
            
        Returns:
            List of related Opportunity records
        """
        self.log_info("Fetching related opportunities")
        
        exclude_clause = f"AND Id != '{exclude_id}'" if exclude_id else ""
        
        query = f"""
        SELECT Id, Name, StageName, Amount, CloseDate, Type,
               Probability, CreatedDate, OwnerId, Owner.Name
        FROM Opportunity
        WHERE AccountId = '{account_id}' {exclude_clause}
        ORDER BY CreatedDate DESC
        LIMIT 20
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            opportunities = result["records"]
            self.log_success(f"Found {len(opportunities)} related opportunities")
            self.relationship_stats["object_counts"]["related_opportunities"] = len(opportunities)
            return opportunities
        
        self.log_info("No related opportunities found")
        return []
    
    def get_quotes(self, opportunity_id: str) -> List[Dict]:
        """
        Get quotes related to an opportunity
        
        Args:
            opportunity_id: Opportunity ID
            
        Returns:
            List of Quote records
        """
        self.log_info("Fetching quotes")
        
        query = f"""
        SELECT Id, Name, QuoteNumber, Status, ExpirationDate,
               TotalPrice, GrandTotal, CreatedDate,
               OwnerId, Owner.Name, IsSyncing, Email
        FROM Quote
        WHERE OpportunityId = '{opportunity_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            quotes = result["records"]
            self.log_success(f"Found {len(quotes)} quotes")
            self.relationship_stats["object_counts"]["quotes"] = len(quotes)
            return quotes
        
        self.log_info("No quotes found")
        return []
    
    def get_contracts(self, account_id: str) -> List[Dict]:
        """
        Get contracts for an account
        
        Args:
            account_id: Account ID
            
        Returns:
            List of Contract records
        """
        self.log_info("Fetching contracts")
        
        query = f"""
        SELECT Id, ContractNumber, Status, StartDate, EndDate,
               ContractTerm, OwnerExpirationNotice, OwnerId, Owner.Name,
               CreatedDate, LastModifiedDate
        FROM Contract
        WHERE AccountId = '{account_id}'
        ORDER BY CreatedDate DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            contracts = result["records"]
            self.log_success(f"Found {len(contracts)} contracts")
            self.relationship_stats["object_counts"]["contracts"] = len(contracts)
            return contracts
        
        self.log_info("No contracts found")
        return []
    
    def analyze_activity_patterns(self, tasks: List[Dict], events: List[Dict]) -> Dict:
        """
        Analyze activity patterns from tasks and events
        
        Args:
            tasks: List of Task records
            events: List of Event records
            
        Returns:
            Activity analysis dictionary
        """
        analysis = {
            "total_activities": len(tasks) + len(events),
            "tasks_count": len(tasks),
            "events_count": len(events),
            "activity_types": {},
            "owners": {},
            "monthly_activity": {},
            "recent_activity": []
        }
        
        # Analyze tasks
        for task in tasks:
            # Activity types
            task_type = task.get("Type", "Unknown")
            analysis["activity_types"][task_type] = analysis["activity_types"].get(task_type, 0) + 1
            
            # Owners
            owner = task.get("Owner", {}).get("Name", "Unknown")
            analysis["owners"][owner] = analysis["owners"].get(owner, 0) + 1
            
            # Monthly activity
            created_date = task.get("CreatedDate", "")
            if created_date:
                month = created_date[:7]  # YYYY-MM
                analysis["monthly_activity"][month] = analysis["monthly_activity"].get(month, 0) + 1
            
            # Recent activity (last 30 days)
            if task.get("ActivityDate"):
                analysis["recent_activity"].append({
                    "type": "task",
                    "subject": task.get("Subject"),
                    "date": task.get("ActivityDate"),
                    "owner": owner
                })
        
        # Analyze events
        for event in events:
            # Activity types
            event_type = event.get("Type", "Meeting")
            analysis["activity_types"][event_type] = analysis["activity_types"].get(event_type, 0) + 1
            
            # Owners
            owner = event.get("Owner", {}).get("Name", "Unknown")
            analysis["owners"][owner] = analysis["owners"].get(owner, 0) + 1
            
            # Monthly activity
            created_date = event.get("CreatedDate", "")
            if created_date:
                month = created_date[:7]  # YYYY-MM
                analysis["monthly_activity"][month] = analysis["monthly_activity"].get(month, 0) + 1
            
            # Recent activity
            if event.get("StartDateTime"):
                analysis["recent_activity"].append({
                    "type": "event",
                    "subject": event.get("Subject"),
                    "date": event.get("StartDateTime")[:10],
                    "owner": owner
                })
        
        # Sort recent activity by date
        analysis["recent_activity"].sort(key=lambda x: x.get("date", ""), reverse=True)
        analysis["recent_activity"] = analysis["recent_activity"][:10]  # Keep top 10
        
        return analysis
    
    def build_relationship_hierarchy(self, opportunity_id: str, account_id: str) -> Dict:
        """
        Build a complete relationship hierarchy
        
        Args:
            opportunity_id: Opportunity ID
            account_id: Account ID
            
        Returns:
            Complete relationship hierarchy
        """
        self.log_info("Building relationship hierarchy")
        
        hierarchy = {
            "root": {
                "opportunity_id": opportunity_id,
                "account_id": account_id
            },
            "direct_children": {},
            "indirect_children": {},
            "cross_references": {}
        }
        
        # Direct children of opportunity
        opp_tasks = self.get_tasks(opportunity_id, "opportunity")
        opp_events = self.get_events(opportunity_id, "opportunity")
        opp_notes = self.get_notes(opportunity_id, "opportunity")
        opp_emails = self.get_email_messages(opportunity_id, "opportunity")
        quotes = self.get_quotes(opportunity_id)
        
        hierarchy["direct_children"]["opportunity"] = {
            "tasks": opp_tasks,
            "events": opp_events,
            "notes": opp_notes,
            "emails": opp_emails,
            "quotes": quotes
        }
        
        # Direct children of account
        account_cases = self.get_cases(account_id)
        account_contracts = self.get_contracts(account_id)
        related_opps = self.get_related_opportunities(account_id, opportunity_id)
        
        hierarchy["direct_children"]["account"] = {
            "cases": account_cases,
            "contracts": account_contracts,
            "related_opportunities": related_opps
        }
        
        # Cross-references (objects that reference multiple entities)
        feed_items = self.get_feed_items(opportunity_id, "opportunity")
        attachments = self.get_attachments(opportunity_id, "opportunity")
        
        hierarchy["cross_references"] = {
            "feed_items": feed_items,
            "attachments": attachments
        }
        
        return hierarchy
    
    def build_complete_relationship_map(self, opportunity_id: str, account_id: str) -> Dict:
        """
        Build complete relationship map with analysis
        
        Args:
            opportunity_id: Opportunity ID
            account_id: Account ID
            
        Returns:
            Complete relationship map and analysis
        """
        self.log_info("Building complete relationship map")
        
        # Reset stats
        self.relationship_stats = {
            "total_objects": 0,
            "total_relationships": 0,
            "object_counts": {}
        }
        
        # Build hierarchy
        hierarchy = self.build_relationship_hierarchy(opportunity_id, account_id)
        
        # Get all tasks and events for analysis
        all_tasks = hierarchy["direct_children"]["opportunity"]["tasks"]
        all_events = hierarchy["direct_children"]["opportunity"]["events"]
        
        # Analyze patterns
        activity_analysis = self.analyze_activity_patterns(all_tasks, all_events)
        
        # Calculate totals
        for obj_type, count in self.relationship_stats["object_counts"].items():
            self.relationship_stats["total_objects"] += count
        
        relationship_map = {
            "hierarchy": hierarchy,
            "analysis": {
                "activity_patterns": activity_analysis,
                "object_summary": self.relationship_stats["object_counts"],
                "total_objects": self.relationship_stats["total_objects"]
            },
            "metadata": {
                "extraction_stats": self.get_extraction_stats(),
                "relationship_stats": self.relationship_stats
            }
        }
        
        total_objects = self.relationship_stats["total_objects"]
        self.log_success(f"Relationship mapping complete: {total_objects} total objects mapped")
        
        return relationship_map
    
    def get_object_connections(self, relationships: Dict) -> List[Tuple[str, str, str]]:
        """
        Extract object connections for visualization
        
        Args:
            relationships: Relationship map
            
        Returns:
            List of (source, target, relationship_type) tuples
        """
        connections = []
        
        hierarchy = relationships.get("hierarchy", {})
        root = hierarchy.get("root", {})
        
        opp_id = root.get("opportunity_id")
        account_id = root.get("account_id")
        
        if opp_id and account_id:
            connections.append((account_id, opp_id, "owns"))
        
        # Add direct children connections
        for parent_type, children in hierarchy.get("direct_children", {}).items():
            parent_id = root.get(f"{parent_type}_id")
            if parent_id:
                for child_type, child_records in children.items():
                    for record in child_records:
                        child_id = record.get("Id")
                        if child_id:
                            connections.append((parent_id, child_id, f"has_{child_type}"))
        
        return connections
    
    def get_current_relationships(self) -> Dict:
        """Get currently loaded relationships"""
        return self.relationships
    
    def get_relationship_stats(self) -> Dict:
        """Get relationship mapping statistics"""
        return self.relationship_stats.copy()