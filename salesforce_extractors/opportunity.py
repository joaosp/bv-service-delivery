"""
Opportunity and Account Extractor

Handles extraction of opportunity and related account data from Salesforce.
"""

from typing import Dict, List, Optional
from .base import SalesforceBase


class OpportunityExtractor(SalesforceBase):
    """Extracts opportunity and account data from Salesforce"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        super().__init__(org_username)
        self.opportunity_data = {}
        self.account_data = {}
    
    def get_by_id(self, opp_id: str) -> Optional[Dict]:
        """
        Fetch opportunity details by ID
        
        Args:
            opp_id: Salesforce opportunity ID
            
        Returns:
            Opportunity data dictionary or None if not found
        """
        self.log_info(f"Fetching opportunity: {opp_id}")
        
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
            self.log_success(f"Found opportunity: {self.opportunity_data.get('Name')}")
            return self.opportunity_data
        
        self.log_error(f"Opportunity not found: {opp_id}")
        return None
    
    def get_by_name(self, opp_name: str) -> Optional[Dict]:
        """
        Fetch opportunity details by name (searches for partial matches)
        
        Args:
            opp_name: Opportunity name to search for
            
        Returns:
            Opportunity data dictionary or None if not found/multiple matches
        """
        self.log_info(f"Searching for opportunity: {opp_name}")
        
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
                self.log_success(f"Found opportunity: {self.opportunity_data.get('Name')}")
                return self.opportunity_data
            else:
                self.log_warning("Multiple opportunities found:")
                for i, opp in enumerate(result["records"], 1):
                    print(f"  {i}. {opp['Name']} (ID: {opp['Id']}) - Stage: {opp['StageName']}")
                self.log_error("Please use specific opportunity ID instead")
                return None
        
        self.log_error(f"No opportunities found matching: {opp_name}")
        return None
    
    def get_account_details(self, account_id: str = None) -> Optional[Dict]:
        """
        Fetch related account information
        
        Args:
            account_id: Account ID (if None, uses opportunity's AccountId)
            
        Returns:
            Account data dictionary or None if not found
        """
        if not account_id:
            if not self.opportunity_data.get("AccountId"):
                self.log_error("No account ID available")
                return None
            account_id = self.opportunity_data["AccountId"]
        
        self.log_info(f"Fetching account details for: {account_id}")
        
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
            self.log_success(f"Found account: {self.account_data.get('Name')}")
            return self.account_data
        
        self.log_error(f"Account not found: {account_id}")
        return None
    
    def get_opportunity_products(self, opp_id: str = None) -> List[Dict]:
        """
        Get opportunity line items (products)
        
        Args:
            opp_id: Opportunity ID (if None, uses current opportunity)
            
        Returns:
            List of opportunity line items
        """
        if not opp_id:
            if not self.opportunity_data.get("Id"):
                self.log_error("No opportunity ID available")
                return []
            opp_id = self.opportunity_data["Id"]
        
        self.log_info("Fetching opportunity products")
        
        query = f"""
        SELECT Id, Product2Id, Product2.Name, Product2.ProductCode,
               Quantity, UnitPrice, TotalPrice, Description,
               PricebookEntry.Name, ServiceDate, CreatedDate
        FROM OpportunityLineItem
        WHERE OpportunityId = '{opp_id}'
        ORDER BY CreatedDate
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            products = result["records"]
            self.log_success(f"Found {len(products)} opportunity products")
            return products
        
        self.log_info("No opportunity products found")
        return []
    
    def get_opportunity_history(self, opp_id: str = None) -> List[Dict]:
        """
        Get opportunity field history
        
        Args:
            opp_id: Opportunity ID (if None, uses current opportunity)
            
        Returns:
            List of opportunity history records
        """
        if not opp_id:
            if not self.opportunity_data.get("Id"):
                self.log_error("No opportunity ID available")
                return []
            opp_id = self.opportunity_data["Id"]
        
        self.log_info("Fetching opportunity history")
        
        query = f"""
        SELECT Id, OpportunityId, StageName, Amount, PrevAmount, 
               CloseDate, PrevCloseDate, Probability, ForecastCategory,
               CreatedDate, CreatedById
        FROM OpportunityHistory
        WHERE OpportunityId = '{opp_id}'
        ORDER BY CreatedDate DESC
        LIMIT 100
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            history = result["records"]
            self.log_success(f"Found {len(history)} opportunity history records")
            return history
        
        self.log_info("No opportunity history found")
        return []
    
    def get_opportunity_team(self, opp_id: str = None) -> List[Dict]:
        """
        Get opportunity team members
        
        Args:
            opp_id: Opportunity ID (if None, uses current opportunity)
            
        Returns:
            List of opportunity team members
        """
        if not opp_id:
            if not self.opportunity_data.get("Id"):
                self.log_error("No opportunity ID available")
                return []
            opp_id = self.opportunity_data["Id"]
        
        self.log_info("Fetching opportunity team")
        
        query = f"""
        SELECT Id, UserId, User.Name, User.Email, TeamMemberRole,
               OpportunityAccessLevel, CreatedDate
        FROM OpportunityTeamMember
        WHERE OpportunityId = '{opp_id}'
        ORDER BY CreatedDate
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            team = result["records"]
            self.log_success(f"Found {len(team)} opportunity team members")
            return team
        
        self.log_info("No opportunity team found")
        return []
    
    def get_complete_opportunity_data(self, opp_id_or_name: str) -> Dict:
        """
        Get complete opportunity data including account, products, history, and team
        
        Args:
            opp_id_or_name: Opportunity ID or name
            
        Returns:
            Complete opportunity data dictionary
        """
        # Determine if input is ID or name
        if len(opp_id_or_name) == 18 or len(opp_id_or_name) == 15:
            opportunity = self.get_by_id(opp_id_or_name)
        else:
            opportunity = self.get_by_name(opp_id_or_name)
        
        if not opportunity:
            return {}
        
        # Get related data
        account = self.get_account_details()
        products = self.get_opportunity_products()
        history = self.get_opportunity_history()
        team = self.get_opportunity_team()
        
        return {
            "opportunity": opportunity,
            "account": account,
            "products": products,
            "history": history,
            "team": team,
            "extraction_stats": self.get_extraction_stats()
        }
    
    def get_current_opportunity(self) -> Dict:
        """Get currently loaded opportunity data"""
        return self.opportunity_data
    
    def get_current_account(self) -> Dict:
        """Get currently loaded account data"""
        return self.account_data
    
    def get_opportunity_id(self) -> Optional[str]:
        """Get current opportunity ID"""
        return self.opportunity_data.get("Id")
    
    def get_account_id(self) -> Optional[str]:
        """Get current account ID"""
        return self.opportunity_data.get("AccountId") or self.account_data.get("Id")