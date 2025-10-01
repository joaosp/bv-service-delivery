#!/usr/bin/env python3
"""
Test Transcript Extraction for Any Salesforce Opportunity

Tests the complete transcript extraction pipeline including:
- VoiceCall extraction
- VideoCall extraction
- Microsoft Teams transcript integration
- Azure Graph API connectivity
- Data validation and output
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Load environment variables from .env file
from dotenv import load_dotenv

# Add parent directory to path to import salesforce_extractors
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from salesforce_extractors import TranscriptExtractor, OpportunityExtractor, utils

# Load .env from bv-provisioning-agent directory
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment variables from: {env_path}")
else:
    print(f"ℹ️  No .env file found at: {env_path}")


class TranscriptExtractionTester:
    """Test harness for transcript extraction from Salesforce opportunities"""

    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        self.org_username = org_username
        self.transcript_extractor = TranscriptExtractor(org_username)
        self.opportunity_extractor = OpportunityExtractor(org_username)
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "tests_passed": 0,
            "tests_failed": 0,
            "test_details": []
        }

    def log_test(self, test_name: str, passed: bool, message: str, details: Optional[Dict] = None):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status} - {test_name}")
        print(f"  {message}")

        if details:
            for key, value in details.items():
                print(f"  {key}: {value}")

        self.test_results["test_details"].append({
            "test_name": test_name,
            "passed": passed,
            "message": message,
            "details": details or {}
        })

        if passed:
            self.test_results["tests_passed"] += 1
        else:
            self.test_results["tests_failed"] += 1

    def test_opportunity_exists(self, opp_id: str) -> Optional[Dict]:
        """Test that opportunity exists and is accessible"""
        print(f"\n🔍 Testing Opportunity Access: {opp_id}")

        try:
            opportunity = self.opportunity_extractor.get_by_id(opp_id)

            if opportunity:
                opp_name = opportunity.get("Name", "Unknown")
                account_id = opportunity.get("AccountId")

                self.log_test(
                    "Opportunity Access",
                    True,
                    f"Successfully retrieved opportunity: {opp_name}",
                    {
                        "opportunity_id": opp_id,
                        "account_id": account_id,
                        "name": opp_name,
                        "stage": opportunity.get("StageName")
                    }
                )
                return opportunity
            else:
                self.log_test(
                    "Opportunity Access",
                    False,
                    f"Could not retrieve opportunity: {opp_id}"
                )
                return None

        except Exception as e:
            self.log_test(
                "Opportunity Access",
                False,
                f"Error accessing opportunity: {str(e)}"
            )
            return None

    def test_azure_credentials(self) -> bool:
        """Test Azure credentials are configured"""
        print("\n🔐 Testing Azure Credentials")

        client_id = os.getenv('AZURE_CLIENT_ID')
        client_secret = os.getenv('AZURE_CLIENT_SECRET')
        tenant_id = os.getenv('AZURE_TENANT_ID')

        has_credentials = all([client_id, client_secret, tenant_id])

        if has_credentials:
            self.log_test(
                "Azure Credentials",
                True,
                "Azure credentials are configured",
                {
                    "client_id": client_id[:8] + "..." if client_id else None,
                    "tenant_id": tenant_id[:8] + "..." if tenant_id else None,
                    "credentials_ready": "Yes"
                }
            )
        else:
            missing = []
            if not client_id:
                missing.append("AZURE_CLIENT_ID")
            if not client_secret:
                missing.append("AZURE_CLIENT_SECRET")
            if not tenant_id:
                missing.append("AZURE_TENANT_ID")

            self.log_test(
                "Azure Credentials",
                False,
                "Azure credentials not configured - Teams transcript extraction will be skipped",
                {
                    "missing_vars": ", ".join(missing),
                    "note": "Set environment variables to enable Teams integration"
                }
            )

        return has_credentials

    def test_voice_call_extraction(self, opp_id: str, account_id: str) -> Dict:
        """Test VoiceCall extraction"""
        print("\n📞 Testing VoiceCall Extraction")

        try:
            # Try opportunity first
            voice_calls = self.transcript_extractor.get_voice_calls(opp_id)

            # If none found, try account
            if not voice_calls:
                voice_calls = self.transcript_extractor.get_voice_calls_by_account(account_id)

            self.log_test(
                "VoiceCall Extraction",
                True,
                f"VoiceCall query executed successfully",
                {
                    "voice_calls_found": len(voice_calls),
                    "has_calls": "Yes" if voice_calls else "No"
                }
            )

            return {
                "voice_calls": voice_calls,
                "count": len(voice_calls)
            }

        except Exception as e:
            self.log_test(
                "VoiceCall Extraction",
                False,
                f"Error extracting voice calls: {str(e)}"
            )
            return {"voice_calls": [], "count": 0}

    def test_video_call_extraction(self, opp_id: str) -> Dict:
        """Test VideoCall extraction"""
        print("\n🎥 Testing VideoCall Extraction")

        try:
            video_calls = self.transcript_extractor.get_video_calls(opp_id)

            # Check for Teams meetings
            teams_calls = [vc for vc in video_calls if vc.get('VendorName', '').lower() == 'msteams']

            self.log_test(
                "VideoCall Extraction",
                True,
                f"VideoCall query executed successfully",
                {
                    "video_calls_found": len(video_calls),
                    "teams_calls_found": len(teams_calls),
                    "has_teams_calls": "Yes" if teams_calls else "No"
                }
            )

            return {
                "video_calls": video_calls,
                "teams_calls": teams_calls,
                "count": len(video_calls)
            }

        except Exception as e:
            self.log_test(
                "VideoCall Extraction",
                False,
                f"Error extracting video calls: {str(e)}"
            )
            return {"video_calls": [], "teams_calls": [], "count": 0}

    def test_teams_transcript_extraction(self, video_calls: list, output_dir: Path, has_azure: bool) -> Dict:
        """Test Teams transcript extraction"""
        print("\n📝 Testing Teams Transcript Extraction")

        teams_calls = [vc for vc in video_calls if vc.get('VendorName', '').lower() == 'msteams']

        if not teams_calls:
            self.log_test(
                "Teams Transcript Extraction",
                True,
                "No Teams meetings found - skipping Teams transcript extraction",
                {"teams_meetings": 0}
            )
            return {"transcripts_extracted": 0, "success": True}

        if not has_azure:
            self.log_test(
                "Teams Transcript Extraction",
                True,
                f"Found {len(teams_calls)} Teams meetings but Azure credentials not configured - skipping extraction",
                {
                    "teams_meetings": len(teams_calls),
                    "note": "Configure Azure credentials to enable extraction"
                }
            )
            return {"transcripts_extracted": 0, "success": True}

        # Try to extract Teams transcripts
        extracted_count = 0
        errors = []

        for teams_call in teams_calls:
            try:
                transcript_data = self.transcript_extractor.extract_teams_transcript(
                    teams_call, output_dir
                )

                if transcript_data:
                    extracted_count += 1

            except Exception as e:
                errors.append(str(e))

        success = extracted_count > 0 or len(errors) == 0

        self.log_test(
            "Teams Transcript Extraction",
            success,
            f"Teams transcript extraction completed",
            {
                "teams_meetings": len(teams_calls),
                "transcripts_extracted": extracted_count,
                "errors": len(errors)
            }
        )

        return {
            "transcripts_extracted": extracted_count,
            "errors": errors,
            "success": success
        }

    def test_complete_extraction(self, opp_id: str, output_dir: Path) -> Dict:
        """Test complete transcript extraction pipeline"""
        print("\n🚀 Testing Complete Extraction Pipeline")

        try:
            # Get opportunity details first
            opportunity = self.opportunity_extractor.get_by_id(opp_id)
            if not opportunity:
                self.log_test(
                    "Complete Extraction",
                    False,
                    "Could not retrieve opportunity for extraction"
                )
                return {}

            account_id = opportunity.get("AccountId")
            opp_name = opportunity.get("Name")

            # Run complete extraction with opportunity name for better VideoCall search
            results = self.transcript_extractor.extract_all_transcripts(
                opp_id, account_id, output_dir, opp_name
            )

            # Validate results structure
            expected_keys = ["transcripts", "voice_calls", "video_calls",
                           "messaging_sessions", "insights", "stats", "extraction_stats"]
            has_all_keys = all(key in results for key in expected_keys)

            stats = results.get("stats", {})
            extraction_stats = results.get("extraction_stats", {})

            self.log_test(
                "Complete Extraction",
                has_all_keys,
                "Complete extraction pipeline executed",
                {
                    "transcripts_extracted": stats.get("transcripts_extracted", 0),
                    "voice_calls_found": stats.get("voice_calls_found", 0),
                    "video_calls_found": stats.get("video_calls_found", 0),
                    "teams_transcripts": stats.get("teams_transcripts_found", 0),
                    "queries_executed": extraction_stats.get("queries_executed", 0),
                    "errors": len(stats.get("errors", []))
                }
            )

            return results

        except Exception as e:
            self.log_test(
                "Complete Extraction",
                False,
                f"Error during complete extraction: {str(e)}"
            )
            return {}

    def run_tests(self, opp_id: str, output_base_dir: Optional[str] = None) -> bool:
        """
        Run all tests for transcript extraction

        Args:
            opp_id: Salesforce opportunity ID
            output_base_dir: Base directory for output (default: data/)

        Returns:
            True if all tests passed
        """
        print("=" * 70)
        print("🧪 TRANSCRIPT EXTRACTION TEST SUITE")
        print("=" * 70)
        print(f"Opportunity ID: {opp_id}")
        print(f"Org: {self.org_username}")
        print(f"Timestamp: {self.test_results['timestamp']}")

        # Test 1: Opportunity exists
        opportunity = self.test_opportunity_exists(opp_id)
        if not opportunity:
            print("\n❌ Cannot proceed without valid opportunity")
            return False

        account_id = opportunity.get("AccountId")

        # Setup output directory
        if output_base_dir:
            output_dir = Path(output_base_dir) / opp_id
        else:
            output_dir = Path("data") / opp_id

        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📁 Output directory: {output_dir}")

        # Test 2: Azure credentials
        has_azure = self.test_azure_credentials()

        # Test 3: VoiceCall extraction
        voice_results = self.test_voice_call_extraction(opp_id, account_id)

        # Test 4: VideoCall extraction
        video_results = self.test_video_call_extraction(opp_id)

        # Test 5: Teams transcript extraction
        teams_results = self.test_teams_transcript_extraction(
            video_results.get("video_calls", []),
            output_dir,
            has_azure
        )

        # Test 6: Complete extraction pipeline
        complete_results = self.test_complete_extraction(opp_id, output_dir)

        # Save test results
        results_file = output_dir / "test_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                "test_results": self.test_results,
                "extraction_results": {
                    "voice_calls": len(voice_results.get("voice_calls", [])),
                    "video_calls": len(video_results.get("video_calls", [])),
                    "teams_calls": len(video_results.get("teams_calls", [])),
                    "teams_transcripts": teams_results.get("transcripts_extracted", 0),
                    "complete_extraction": complete_results.get("stats", {})
                }
            }, f, indent=2, default=str)

        print(f"\n💾 Test results saved to: {results_file}")

        # Print summary
        print("\n" + "=" * 70)
        print("📊 TEST SUMMARY")
        print("=" * 70)
        print(f"Tests Passed: {self.test_results['tests_passed']}")
        print(f"Tests Failed: {self.test_results['tests_failed']}")
        print(f"Total Tests: {self.test_results['tests_passed'] + self.test_results['tests_failed']}")

        all_passed = self.test_results['tests_failed'] == 0

        if all_passed:
            print("\n✅ ALL TESTS PASSED")
        else:
            print(f"\n❌ {self.test_results['tests_failed']} TEST(S) FAILED")

        print("=" * 70)

        return all_passed


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Test transcript extraction for any Salesforce opportunity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --opp-id 006Pq00000WKi7LIAT
  %(prog)s --opp-id 006ABC123456789 --org myorg@company.com
  %(prog)s --opp-id 006ABC123456789 --output-dir /tmp/tests

Environment Variables (for Teams integration):
  AZURE_CLIENT_ID       - Microsoft Azure application client ID
  AZURE_CLIENT_SECRET   - Microsoft Azure application client secret
  AZURE_TENANT_ID       - Microsoft Azure tenant ID

Without Azure credentials, Teams transcript extraction will be skipped.
        """
    )

    parser.add_argument(
        "--opp-id",
        required=True,
        help="Salesforce opportunity ID (15 or 18 characters)"
    )
    parser.add_argument(
        "--org",
        default="jcamarate@broadvoice.com",
        help="Salesforce org username (default: %(default)s)"
    )
    parser.add_argument(
        "--output-dir",
        help="Base output directory (default: data/)"
    )

    args = parser.parse_args()

    # Validate opportunity ID format
    if not utils.validate_opportunity_id(args.opp_id):
        print(f"❌ Error: Invalid opportunity ID format: {args.opp_id}")
        print("Expected: 15 or 18 character Salesforce ID starting with '006'")
        sys.exit(1)

    try:
        # Create tester and run tests
        tester = TranscriptExtractionTester(org_username=args.org)
        success = tester.run_tests(args.opp_id, args.output_dir)

        # Exit with appropriate code
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n⚠️  Tests cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
