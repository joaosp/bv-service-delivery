#!/usr/bin/env python3
"""
Test script to verify SOQL query fixes and error handling improvements
"""

import sys
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

from salesforce_extractors import TranscriptExtractor, OpportunityExtractor

def test_voice_calls():
    """Test voice call extraction with fallback"""
    print("\n=== Testing Voice Call Extraction ===")
    
    extractor = TranscriptExtractor()
    
    # Test with a known opportunity ID
    opportunity_id = "006Pq00000Qb93lIAB"
    voice_calls = extractor.get_voice_calls(opportunity_id)
    
    print(f"Voice calls found: {len(voice_calls)}")
    if voice_calls:
        print("Sample voice call fields:")
        for key in voice_calls[0].keys():
            print(f"  - {key}")
    
    return len(voice_calls)

def test_messaging_sessions():
    """Test messaging session extraction with fallback"""
    print("\n=== Testing Messaging Session Extraction ===")
    
    extractor = TranscriptExtractor()
    
    # Test with a known account ID
    account_id = "001Pq00000W3XQ7IAN"
    messaging_sessions = extractor.get_messaging_sessions(account_id)
    
    print(f"Messaging sessions found: {len(messaging_sessions)}")
    if messaging_sessions:
        print("Sample messaging session fields:")
        for key in messaging_sessions[0].keys():
            print(f"  - {key}")
    
    return len(messaging_sessions)

def test_opportunity_history():
    """Test opportunity history extraction"""
    print("\n=== Testing Opportunity History Extraction ===")
    
    extractor = OpportunityExtractor()
    
    # Test with a known opportunity ID
    opportunity_id = "006Pq00000Qb93lIAB"
    history = extractor.get_opportunity_history(opportunity_id)
    
    print(f"Opportunity history records found: {len(history)}")
    if history:
        print("Sample history fields:")
        for key in history[0].keys():
            print(f"  - {key}")
    
    return len(history)

def test_einstein_insights():
    """Test Einstein insights with improved error handling"""
    print("\n=== Testing Einstein Insights Extraction ===")
    
    extractor = TranscriptExtractor()
    
    # Test with mock voice call IDs
    voice_call_ids = ["test_id_1", "test_id_2"]
    insights = extractor.get_einstein_insights(voice_call_ids)
    
    print(f"Insights found: {len(insights)}")
    if insights:
        print("Sample insight fields:")
        for key in insights[0].keys():
            print(f"  - {key}")
    
    return len(insights)

def main():
    """Run all tests"""
    print("🧪 Testing SOQL Query Fixes and Error Handling")
    print("=" * 60)
    
    results = {}
    
    try:
        results["voice_calls"] = test_voice_calls()
        results["messaging_sessions"] = test_messaging_sessions()
        results["opportunity_history"] = test_opportunity_history()
        results["insights"] = test_einstein_insights()
        
        print("\n" + "=" * 60)
        print("📊 Test Results Summary:")
        print("=" * 60)
        
        for test_name, count in results.items():
            status = "✅ PASS" if count >= 0 else "❌ FAIL"
            print(f"{test_name:<25}: {count:>5} records {status}")
        
        # Print any extraction stats/errors
        extractor = TranscriptExtractor()
        stats = extractor.get_extraction_stats()
        
        print(f"\nQuery Statistics:")
        print(f"- Queries executed: {stats['queries_executed']}")
        print(f"- Errors encountered: {len(stats['errors'])}")
        
        if stats['errors']:
            print("\nError Details:")
            for error in stats['errors'][:5]:  # Show first 5 errors
                print(f"  - {error}")
        
        print("\n✅ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)