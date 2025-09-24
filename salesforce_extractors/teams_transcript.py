"""
Microsoft Teams Transcript Extractor

Integrates with Microsoft Graph API to fetch meeting transcripts
from Teams meetings linked to Salesforce VideoCall records.
"""

import os
import json
import base64
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import msal
from .base import SalesforceBase


class TeamsTranscriptExtractor(SalesforceBase):
    """Extract transcripts from Microsoft Teams using Graph API"""
    
    def __init__(self, org: str):
        super().__init__(org)
        self.client_id = os.getenv('AZURE_CLIENT_ID')
        self.client_secret = os.getenv('AZURE_CLIENT_SECRET') 
        self.tenant_id = os.getenv('AZURE_TENANT_ID')
        self.graph_base_url = "https://graph.microsoft.com/v1.0"
        self.access_token = None
        
        # Statistics
        self.transcript_stats = {
            "teams_meetings_found": 0,
            "transcripts_found": 0,
            "transcripts_downloaded": 0,
            "errors": []
        }
    
    def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API using client credentials
        
        Returns:
            bool: True if authentication successful
        """
        if not all([self.client_id, self.client_secret, self.tenant_id]):
            self.log_error("Missing Azure AD credentials. Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID")
            return False
        
        try:
            # Create MSAL app instance
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
            
            # Acquire token for Microsoft Graph
            result = app.acquire_token_silent(
                scopes=["https://graph.microsoft.com/.default"],
                account=None
            )
            
            if not result:
                result = app.acquire_token_for_client(
                    scopes=["https://graph.microsoft.com/.default"]
                )
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                self.log_success("Successfully authenticated with Microsoft Graph")
                return True
            else:
                error_msg = result.get("error_description", "Unknown authentication error")
                self.log_error(f"Graph authentication failed: {error_msg}")
                return False
                
        except Exception as e:
            self.log_error(f"Exception during authentication: {str(e)}")
            return False
    
    def parse_vendor_meeting_key(self, vendor_meeting_key: str) -> Dict[str, str]:
        """
        Parse VendorMeetingKey to extract Teams meeting identifiers
        
        Args:
            vendor_meeting_key: Base64 encoded meeting key from Salesforce
            
        Returns:
            Dict with parsed identifiers
        """
        try:
            # Decode base64
            decoded = base64.b64decode(vendor_meeting_key).decode('utf-8')
            self.log_info(f"Decoded meeting key: {decoded}")
            
            # Parse format: "1*{organizer-id}*0**{thread-info}"
            parts = decoded.split('*')
            
            if len(parts) >= 4:
                organizer_id = parts[1]
                thread_info = parts[4]  # Contains the thread ID
                
                # Extract thread ID from format: "19:meeting_{base64_thread_id}@thread.v2"
                if "19:meeting_" in thread_info and "@thread.v2" in thread_info:
                    thread_part = thread_info.split("19:meeting_")[1].split("@thread.v2")[0]
                    thread_id = base64.b64decode(thread_part).decode('utf-8')
                    
                    return {
                        "organizer_id": organizer_id,
                        "thread_id": thread_id,
                        "thread_info": thread_info,
                        "full_decoded": decoded
                    }
            
            self.log_warning(f"Could not parse meeting key format: {decoded}")
            return {}
            
        except Exception as e:
            self.log_error(f"Error parsing vendor meeting key: {str(e)}")
            return {}
    
    def find_online_meeting(self, organizer_id: str, meeting_uuid: str, 
                           start_time: str) -> Optional[str]:
        """
        Find online meeting ID using Graph API
        
        Args:
            organizer_id: Meeting organizer user ID
            meeting_uuid: VendorMeetingUuid from VideoCall
            start_time: Meeting start time ISO format
            
        Returns:
            Online meeting ID if found
        """
        if not self.access_token:
            self.log_error("Not authenticated with Graph API")
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Try to find meeting by organizer and time range
            # Note: This is a simplified approach - in production you might need
            # to search calendar events or use more specific filters
            url = f"{self.graph_base_url}/users/{organizer_id}/onlineMeetings"
            
            # Add date filter if possible
            start_date = datetime.fromisoformat(start_time.replace('Z', '+00:00')).date()
            url += f"?$filter=startDateTime ge {start_date}T00:00:00Z and startDateTime lt {start_date}T23:59:59Z"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                meetings = response.json().get('value', [])
                self.log_info(f"Found {len(meetings)} online meetings for organizer")
                
                # Try to match by UUID or other identifiers
                for meeting in meetings:
                    meeting_id = meeting.get('id')
                    if meeting_id:
                        self.log_success(f"Found potential meeting: {meeting_id}")
                        return meeting_id
                        
                # If no exact match, return first meeting (fallback)
                if meetings:
                    return meetings[0].get('id')
            else:
                self.log_error(f"Failed to fetch meetings: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.log_error(f"Error finding online meeting: {str(e)}")
        
        return None
    
    def get_meeting_transcripts(self, organizer_id: str, meeting_id: str) -> List[Dict]:
        """
        Get all transcripts for a Teams meeting
        
        Args:
            organizer_id: Meeting organizer user ID
            meeting_id: Online meeting ID
            
        Returns:
            List of transcript metadata
        """
        if not self.access_token:
            self.log_error("Not authenticated with Graph API")
            return []
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.graph_base_url}/users/{organizer_id}/onlineMeetings/{meeting_id}/transcripts"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                transcripts = response.json().get('value', [])
                self.log_success(f"Found {len(transcripts)} transcripts for meeting")
                self.transcript_stats["transcripts_found"] = len(transcripts)
                return transcripts
            else:
                error_msg = f"Failed to fetch transcripts: {response.status_code} - {response.text}"
                self.log_error(error_msg)
                self.transcript_stats["errors"].append(error_msg)
                
        except Exception as e:
            error_msg = f"Error getting meeting transcripts: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
        
        return []
    
    def download_transcript_content(self, organizer_id: str, meeting_id: str, 
                                   transcript_id: str, format: str = "text/vtt") -> Optional[str]:
        """
        Download transcript content
        
        Args:
            organizer_id: Meeting organizer user ID
            meeting_id: Online meeting ID
            transcript_id: Transcript ID
            format: Content format (text/vtt, text/plain, etc.)
            
        Returns:
            Transcript content as string
        """
        if not self.access_token:
            self.log_error("Not authenticated with Graph API")
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
            }
            
            url = f"{self.graph_base_url}/users/{organizer_id}/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content"
            
            # Add format parameter if specified
            if format:
                url += f"?$format={format}"
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                content = response.text
                self.log_success(f"Downloaded transcript content ({len(content)} chars)")
                self.transcript_stats["transcripts_downloaded"] += 1
                return content
            else:
                error_msg = f"Failed to download transcript: {response.status_code} - {response.text}"
                self.log_error(error_msg)
                self.transcript_stats["errors"].append(error_msg)
                
        except Exception as e:
            error_msg = f"Error downloading transcript content: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
        
        return None
    
    def extract_teams_transcript(self, video_call_data: Dict) -> Optional[Dict]:
        """
        Extract Teams transcript for a VideoCall record
        
        Args:
            video_call_data: VideoCall record data from Salesforce
            
        Returns:
            Dict with transcript data and metadata
        """
        try:
            # Check if this is a Teams meeting
            vendor_name = video_call_data.get('VendorName', '').lower()
            if vendor_name != 'msteams':
                self.log_info(f"Skipping non-Teams meeting: {vendor_name}")
                return None
            
            # Extract required identifiers
            vendor_meeting_key = video_call_data.get('VendorMeetingKey')
            meeting_uuid = video_call_data.get('VendorMeetingUuid')
            start_time = video_call_data.get('StartDateTime')
            
            if not all([vendor_meeting_key, meeting_uuid, start_time]):
                self.log_error("Missing required Teams meeting identifiers")
                return None
            
            # Authenticate with Graph API
            if not self.authenticate():
                return None
            
            # Parse meeting identifiers
            parsed_keys = self.parse_vendor_meeting_key(vendor_meeting_key)
            organizer_id = parsed_keys.get('organizer_id')
            
            if not organizer_id:
                self.log_error("Could not extract organizer ID from meeting key")
                return None
            
            self.log_info(f"Extracting transcript for organizer: {organizer_id}")
            
            # Find the online meeting
            meeting_id = self.find_online_meeting(organizer_id, meeting_uuid, start_time)
            if not meeting_id:
                self.log_error("Could not find online meeting ID")
                return None
            
            self.transcript_stats["teams_meetings_found"] = 1
            
            # Get transcripts
            transcripts = self.get_meeting_transcripts(organizer_id, meeting_id)
            if not transcripts:
                self.log_warning("No transcripts found for meeting")
                return None
            
            # Download transcript content (get the first/primary transcript)
            transcript = transcripts[0]
            transcript_id = transcript.get('id')
            
            if transcript_id:
                # Try VTT format first, fallback to plain text
                content = self.download_transcript_content(
                    organizer_id, meeting_id, transcript_id, "text/vtt"
                )
                
                if not content:
                    content = self.download_transcript_content(
                        organizer_id, meeting_id, transcript_id, "text/plain"
                    )
                
                if content:
                    return {
                        "transcript_id": transcript_id,
                        "meeting_id": meeting_id,
                        "organizer_id": organizer_id,
                        "content": content,
                        "metadata": transcript,
                        "format": "vtt" if "WEBVTT" in content else "plain",
                        "extracted_at": datetime.now().isoformat()
                    }
            
            self.log_error("Could not download transcript content")
            return None
            
        except Exception as e:
            error_msg = f"Error extracting Teams transcript: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
            return None
    
    def save_transcript(self, transcript_data: Dict, output_path: str) -> bool:
        """
        Save transcript to file
        
        Args:
            transcript_data: Transcript data from extract_teams_transcript
            output_path: Path to save transcript file
            
        Returns:
            True if saved successfully
        """
        try:
            # Save transcript content
            content_path = f"{output_path}.txt"
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(transcript_data['content'])
            
            # Save metadata
            metadata_path = f"{output_path}_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, default=str)
            
            self.log_success(f"Saved transcript to {content_path}")
            return True
            
        except Exception as e:
            self.log_error(f"Error saving transcript: {str(e)}")
            return False