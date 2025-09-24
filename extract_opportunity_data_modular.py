#!/usr/bin/env python3
"""
Salesforce Opportunity Data Extractor (Modular Version)

Comprehensive data extraction for Salesforce opportunities using modular extractors.
Extracts all related data including:
- Opportunity and Account details
- Contacts and roles  
- Related objects (Tasks, Events, Cases, etc.)
- Documents and attachments
- Call transcripts and conversations
- Generates comprehensive reports with Mermaid visualizations
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Import our modular extractors
from salesforce_extractors import (
    OpportunityExtractor,
    ContactExtractor, 
    DocumentExtractor,
    TranscriptExtractor,
    RelationshipMapper,
    ReportGenerator,
    utils
)


class OpportunityDataPipeline:
    """Orchestrates complete opportunity data extraction using modular components"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        """
        Initialize the extraction pipeline
        
        Args:
            org_username: Salesforce org username
        """
        self.org_username = org_username
        self.opportunity_id = None
        self.account_id = None
        self.output_dir = None
        
        # Initialize extractors
        self.opportunity_extractor = OpportunityExtractor(org_username)
        self.contact_extractor = ContactExtractor(org_username)
        self.document_extractor = DocumentExtractor(org_username)
        self.transcript_extractor = TranscriptExtractor(org_username)
        self.relationship_mapper = RelationshipMapper(org_username)
        self.report_generator = ReportGenerator()
        
        # Combined results
        self.results = {}
        
    def extract_opportunity_data(self, opp_id_or_name: str) -> bool:
        """
        Main extraction workflow
        
        Args:
            opp_id_or_name: Opportunity ID or name to extract
            
        Returns:
            True if successful, False otherwise
        """
        print("=" * 70)
        print("🚀 MODULAR SALESFORCE OPPORTUNITY DATA EXTRACTOR")
        print("=" * 70)
        
        start_time = datetime.now()
        
        # Step 1: Extract opportunity and account data
        print(f"\n🎯 Step 1: Extracting Opportunity Data")
        opportunity_data = self._extract_opportunity(opp_id_or_name)
        if not opportunity_data:
            print("❌ Failed to extract opportunity data")
            return False
        
        # Setup directories
        self.opportunity_id = opportunity_data["opportunity"]["Id"]
        self.account_id = opportunity_data["opportunity"]["AccountId"]
        self.output_dir = utils.setup_directories(".", self.opportunity_id)
        
        print(f"📁 Created directory structure: {self.output_dir}")
        
        # Step 2: Extract contacts
        print(f"\n👥 Step 2: Extracting Contact Data")
        contacts_data = self._extract_contacts()
        
        # Log contact extraction results
        if contacts_data:
            contact_count = len(contacts_data.get("contacts", []))
            role_count = len(contacts_data.get("contact_roles", []))
            print(f"   ✅ Found {contact_count} contacts and {role_count} contact roles")
            if contacts_data.get("extraction_error"):
                print(f"   ⚠️  Extraction had errors but partial data was preserved")
            if contacts_data.get("partial_extraction_errors"):
                print(f"   ⚠️  {len(contacts_data['partial_extraction_errors'])} partial extraction errors occurred")
        else:
            print("   ❌ No contact data extracted")
        
        # Step 3: Map relationships
        print(f"\n🔗 Step 3: Mapping Object Relationships")
        relationships_data = self._map_relationships()
        
        # Step 4: Download documents
        print(f"\n📄 Step 4: Downloading Documents")
        documents_data = self._download_documents()
        
        # Step 5: Extract transcripts
        print(f"\n📞 Step 5: Extracting Call Transcripts")
        transcripts_data = self._extract_transcripts()
        
        # Step 6: Generate reports and save data
        print(f"\n📝 Step 6: Generating Reports")
        success = self._generate_outputs(
            opportunity_data, contacts_data, relationships_data,
            documents_data, transcripts_data, start_time
        )
        
        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 70)
        if success:
            print("✅ EXTRACTION COMPLETE!")
            print(f"📁 Data saved to: {self.output_dir}")
            print(f"📊 View summary: {self.output_dir}/summary.md")
            print(f"⏱️  Total time: {duration:.1f} seconds")
        else:
            print("❌ EXTRACTION FAILED!")
            print(f"⏱️  Time elapsed: {duration:.1f} seconds")
        
        print("=" * 70)
        
        return success
    
    def _extract_opportunity(self, opp_id_or_name: str) -> Optional[Dict]:
        """Extract opportunity and account data"""
        try:
            # Determine if input is ID or name
            if utils.validate_opportunity_id(opp_id_or_name):
                opportunity = self.opportunity_extractor.get_by_id(opp_id_or_name)
            else:
                opportunity = self.opportunity_extractor.get_by_name(opp_id_or_name)
            
            if not opportunity:
                return None
            
            # Get account details
            account = self.opportunity_extractor.get_account_details()
            
            # Get additional opportunity data
            products = self.opportunity_extractor.get_opportunity_products()
            history = self.opportunity_extractor.get_opportunity_history()
            team = self.opportunity_extractor.get_opportunity_team()
            
            return {
                "opportunity": opportunity,
                "account": account,
                "products": products,
                "history": history,
                "team": team,
                "extraction_stats": self.opportunity_extractor.get_extraction_stats()
            }
            
        except Exception as e:
            print(f"❌ Error extracting opportunity: {str(e)}")
            return None
    
    def _extract_contacts(self) -> Dict:
        """Extract contact data and analysis"""
        try:
            return self.contact_extractor.get_complete_contact_data(
                self.account_id, self.opportunity_id
            )
        except Exception as e:
            print(f"❌ Error extracting contacts: {str(e)}")
            # Try to get basic contact data at least
            try:
                print("   🔄 Attempting to extract basic contact data...")
                contacts = self.contact_extractor.get_account_contacts(self.account_id)
                contact_roles = self.contact_extractor.get_opportunity_contact_roles(self.opportunity_id)
                
                return {
                    "contacts": contacts,
                    "contact_roles": contact_roles,
                    "activities": {},
                    "hierarchy": {},
                    "analysis": {
                        "primary_contacts": [],
                        "decision_makers": [],
                        "technical_contacts": [],
                        "total_contacts": len(contacts),
                        "contacts_with_roles": len(contact_roles)
                    },
                    "extraction_stats": self.contact_extractor.get_extraction_stats(),
                    "extraction_error": str(e)
                }
            except Exception as fallback_error:
                print(f"❌ Fallback contact extraction also failed: {str(fallback_error)}")
                return {
                    "contacts": [],
                    "contact_roles": [],
                    "activities": {},
                    "hierarchy": {},
                    "analysis": {
                        "primary_contacts": [],
                        "decision_makers": [],
                        "technical_contacts": [],
                        "total_contacts": 0,
                        "contacts_with_roles": 0
                    },
                    "extraction_stats": self.contact_extractor.get_extraction_stats(),
                    "extraction_error": str(e),
                    "fallback_error": str(fallback_error)
                }
    
    def _map_relationships(self) -> Dict:
        """Map all related objects and relationships"""
        try:
            return self.relationship_mapper.build_complete_relationship_map(
                self.opportunity_id, self.account_id
            )
        except Exception as e:
            print(f"❌ Error mapping relationships: {str(e)}")
            return {}
    
    def _download_documents(self) -> Dict:
        """Download all documents and attachments"""
        try:
            # Download documents linked to opportunity
            opp_results = self.document_extractor.download_all_documents(
                self.opportunity_id, self.output_dir
            )
            
            # Also try downloading documents linked to account
            account_results = self.document_extractor.download_all_documents(
                self.account_id, self.output_dir
            )
            
            # Get document inventory
            inventory = self.document_extractor.get_document_inventory()
            
            # Get legacy attachments
            attachments = self.document_extractor.get_attachments(self.opportunity_id)
            
            return {
                "stats": opp_results.get("stats", {}),
                "opportunity_results": opp_results,
                "account_results": account_results,
                "inventory": inventory,
                "attachments": attachments,
                "extraction_stats": self.document_extractor.get_extraction_stats()
            }
            
        except Exception as e:
            print(f"❌ Error downloading documents: {str(e)}")
            return {}
    
    def _extract_transcripts(self) -> Dict:
        """Extract call transcripts from various sources"""
        try:
            return self.transcript_extractor.extract_all_transcripts(
                self.opportunity_id, self.account_id, self.output_dir
            )
        except Exception as e:
            print(f"❌ Error extracting transcripts: {str(e)}")
            return {}
    
    def _generate_outputs(self, opportunity_data: Dict, contacts_data: Dict,
                         relationships_data: Dict, documents_data: Dict,
                         transcripts_data: Dict, start_time: datetime) -> bool:
        """Generate all output files and reports"""
        try:
            # Combine all data
            all_data = {
                "opportunity": opportunity_data,
                "contacts": contacts_data,
                "relationships": relationships_data,
                "documents": documents_data,
                "transcripts": transcripts_data,
                "output_directory": str(self.output_dir),
                "extraction_metadata": {
                    "pipeline_start_time": start_time.isoformat(),
                    "pipeline_end_time": datetime.now().isoformat(),
                    "opportunity_id": self.opportunity_id,
                    "account_id": self.account_id,
                    "org_username": self.org_username
                },
                "extraction_stats": {
                    "opportunity": opportunity_data.get("extraction_stats", {}),
                    "contacts": contacts_data.get("extraction_stats", {}),
                    "relationships": relationships_data.get("metadata", {}).get("extraction_stats", {}),
                    "documents": documents_data.get("extraction_stats", {}),
                    "transcripts": transcripts_data.get("extraction_stats", {}),
                }
            }
            
            # Save individual data files
            print("   💾 Saving individual data files...")
            utils.save_json(opportunity_data, self.output_dir / "opportunity.json")
            utils.save_json(contacts_data, self.output_dir / "contacts.json")
            utils.save_json(relationships_data, self.output_dir / "relationships.json")
            utils.save_json(documents_data, self.output_dir / "documents.json")
            utils.save_json(transcripts_data, self.output_dir / "transcripts.json")
            
            # Save complete metadata
            print("   💾 Saving complete metadata...")
            utils.save_json(all_data, self.output_dir / "complete_data.json")
            
            # Generate summary report
            print("   📝 Generating summary report...")
            report_success = self.report_generator.create_summary_report(
                all_data, self.output_dir / "summary.md"
            )
            
            # Export compact JSON
            print("   💾 Exporting compact data...")
            self.report_generator.export_data_json(
                all_data, self.output_dir / "data_export.json"
            )
            
            # Generate summary statistics
            print("   📊 Calculating summary statistics...")
            summary_stats = utils.create_summary_stats(all_data)
            utils.save_json(summary_stats, self.output_dir / "summary_stats.json")
            
            # Export contacts to CSV
            contacts_list = contacts_data.get("contacts", [])
            if contacts_list and len(contacts_list) > 0:
                print(f"   📋 Exporting {len(contacts_list)} contacts to CSV...")
                self.contact_extractor.export_contacts_csv(
                    self.output_dir / "contacts.csv",
                    contacts_list
                )
            else:
                print("   ℹ️  No contacts to export to CSV")
            
            # Log extraction summary
            utils.log_extraction_summary(summary_stats, self.output_dir)
            
            return report_success
            
        except Exception as e:
            print(f"❌ Error generating outputs: {str(e)}")
            return False
    
    def get_extraction_results(self) -> Dict:
        """Get the complete extraction results"""
        return self.results
    
    def cleanup(self):
        """Cleanup and reset extractors"""
        # Reset stats for all extractors
        self.opportunity_extractor.reset_stats()
        self.contact_extractor.reset_stats()
        self.document_extractor.reset_stats()
        self.transcript_extractor.reset_stats()
        self.relationship_mapper.reset_stats()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Extract comprehensive data from Salesforce opportunities using modular extractors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --opp-id 006Pq00000Qb93lIAB
  %(prog)s --opp-name "Acme Corp Voice System"
  %(prog)s --opp-id 006ABC123456789012 --org myorg@company.com
        """
    )
    
    parser.add_argument(
        "--opp-id",
        help="Opportunity ID (15 or 18-character Salesforce ID)"
    )
    parser.add_argument(
        "--opp-name", 
        help="Opportunity name (will search for matches)"
    )
    parser.add_argument(
        "--org",
        default="jcamarate@broadvoice.com",
        help="Salesforce org username (default: %(default)s)"
    )
    parser.add_argument(
        "--output-dir",
        help="Base output directory (default: current directory)"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Cleanup extractor stats after completion"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.opp_id and not args.opp_name:
        print("❌ Error: Please provide either --opp-id or --opp-name")
        parser.print_help()
        sys.exit(1)
    
    try:
        # Create pipeline
        pipeline = OpportunityDataPipeline(org_username=args.org)
        
        # Run extraction
        opp_identifier = args.opp_id or args.opp_name
        success = pipeline.extract_opportunity_data(opp_identifier)
        
        # Cleanup if requested
        if args.cleanup:
            pipeline.cleanup()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️ Extraction cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()