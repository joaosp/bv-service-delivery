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

    def resolve_user_email(self, user_id: str) -> Optional[str]:
        """
        Resolve Azure AD user ID to email address

        Args:
            user_id: Azure AD user ID (GUID)

        Returns:
            User's email address or None if not found
        """
        if not self.access_token:
            return None

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.graph_base_url}/users/{user_id}?$select=userPrincipalName,mail,displayName"

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                user_data = response.json()
                email = user_data.get('mail') or user_data.get('userPrincipalName')
                display_name = user_data.get('displayName', 'Unknown')
                self.log_info(f"Resolved user: {display_name} ({email})")
                return email
            else:
                self.log_warning(f"Could not resolve user email for ID: {user_id}")
                return None

        except Exception as e:
            self.log_warning(f"Error resolving user email: {str(e)}")
            return None

    def check_access_policy(self, organizer_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if we have access to meetings organized by this user

        Args:
            organizer_id: Azure AD user ID of meeting organizer

        Returns:
            Tuple of (has_access, error_message)
        """
        if not self.access_token:
            return False, "Not authenticated with Graph API"

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            # Note: With application permissions, the /onlineMeetings endpoint requires
            # a filter or specific meeting ID. We can't easily pre-check access without
            # a specific meeting ID, so we'll just resolve the user email for logging.
            # The actual meeting access will provide the real validation.

            organizer_email = self.resolve_user_email(organizer_id)

            # If we can resolve the user, that's a good sign
            if organizer_email:
                self.log_info(f"Pre-check: User exists in Azure AD: {organizer_email}")
                # Cannot pre-validate access policy without specific meeting ID
                # This is a limitation of Microsoft Graph API with application permissions
                return True, None
            else:
                # Can't resolve user - might not exist or no User.Read.All permission
                self.log_warning(f"Pre-check: Could not resolve user {organizer_id} in Azure AD")
                # Still allow to proceed - actual meeting access will give definitive answer
                return True, None

        except Exception as e:
            return False, f"Error checking access policy: {str(e)}"

    def get_transcripts_by_date(self, organizer_id: str, start_time: str, end_time: str) -> List[Dict]:
        """
        Get all transcripts for meetings organized by a user within a date range

        Uses getAllTranscripts endpoint which works reliably for UI-created meetings.
        This approach is more robust than accessing meetings by UUID since Salesforce
        VendorMeetingUuid values don't directly map to Graph API meeting IDs.

        IMPORTANT: Requires OnlineMeetings.Read.All permission and Application Access
        Policy granted for the organizer.

        Args:
            organizer_id: Meeting organizer Azure AD user ID from VendorMeetingKey
            start_time: Meeting start time ISO format (e.g., "2025-08-27T17:57:45.000+0000")
            end_time: Meeting end time ISO format (e.g., "2025-08-27T18:15:23.000+0000")

        Returns:
            List of transcript objects with metadata and content URLs
        """
        if not self.access_token:
            self.log_error("Not authenticated with Graph API")
            return []

        try:
            from datetime import datetime, timedelta

            # Parse times and expand date range to account for timezone issues
            start_dt = datetime.fromisoformat(start_time.replace('+0000', '+00:00').replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('+0000', '+00:00').replace('Z', '+00:00'))

            # Expand range by 1 day on each side for safety
            search_start = (start_dt - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
            search_end = (end_dt + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            # Use getAllTranscripts function-style endpoint
            url = (f"{self.graph_base_url}/users/{organizer_id}/onlineMeetings/"
                   f"getAllTranscripts(meetingOrganizerUserId='{organizer_id}',"
                   f"startDateTime={search_start},endDateTime={search_end})")

            self.log_info(f"Searching transcripts for organizer in date range: {search_start} to {search_end}")
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                transcripts = response.json().get('value', [])
                self.log_success(f"Found {len(transcripts)} transcripts in date range")
                self.transcript_stats["transcripts_found"] = len(transcripts)
                return transcripts

            elif response.status_code == 403:
                error_data = response.json().get('error', {})
                error_msg = error_data.get('message', '')

                # Resolve organizer email for better error message
                organizer_email = self.resolve_user_email(organizer_id)
                organizer_display = organizer_email or organizer_id

                # Determine specific error type
                if 'application access policy' in error_msg.lower() or 'not allowed to perform operations' in error_msg:
                    self.log_error(
                        f"Access Policy Error - Organizer: {organizer_display}\n"
                        f"  The application access policy doesn't cover this user.\n"
                        f"  To grant access, run:\n"
                        f"  Grant-CsApplicationAccessPolicy -PolicyName \"<PolicyName>\" -Identity \"{organizer_display}\"\n"
                        f"  Note: Policy changes take up to 30 minutes to propagate."
                    )
                elif 'OnlineMeetings.Read.All' in error_msg or 'insufficient privileges' in error_msg.lower():
                    self.log_error(
                        "Permission Error: Missing 'OnlineMeetings.Read.All' application permission.\n"
                        "  Add this permission in Azure AD App Registration and grant admin consent."
                    )
                else:
                    self.log_error(f"Access Denied (403) for organizer {organizer_display}: {error_msg}")

            else:
                error_msg = f"Failed to fetch transcripts: {response.status_code} - {response.text[:200]}"
                self.log_error(error_msg)
                self.transcript_stats["errors"].append(error_msg)

        except Exception as e:
            error_msg = f"Error getting transcripts by date: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)

        return []
    
    def download_transcript_content(self, content_url: Optional[str] = None,
                                   organizer_id: Optional[str] = None,
                                   meeting_id: Optional[str] = None,
                                   transcript_id: Optional[str] = None,
                                   format: str = "text/vtt") -> Optional[str]:
        """
        Download transcript content

        Can accept either:
        - A direct content_url (from getAllTranscripts response)
        - Individual IDs to construct the URL (legacy approach)

        Args:
            content_url: Direct transcript content URL (preferred)
            organizer_id: Meeting organizer user ID (if constructing URL)
            meeting_id: Online meeting ID (if constructing URL)
            transcript_id: Transcript ID (if constructing URL)
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
                'Accept': 'text/vtt' if format == 'text/vtt' else 'text/plain'
            }

            # Use direct URL if provided, otherwise construct it
            if content_url:
                # Content URL already includes /content, just add format if not present
                if '?$format=' not in content_url:
                    url = f"{content_url}?$format={format}"
                else:
                    url = content_url
            elif all([organizer_id, meeting_id, transcript_id]):
                url = f"{self.graph_base_url}/users/{organizer_id}/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content?$format={format}"
            else:
                self.log_error("Must provide either content_url or all of (organizer_id, meeting_id, transcript_id)")
                return None

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                content = response.text
                self.log_success(f"Downloaded transcript content ({len(content)} chars)")
                self.transcript_stats["transcripts_downloaded"] += 1
                return content
            else:
                error_msg = f"Failed to download transcript: {response.status_code} - {response.text[:200]}"
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

        Uses the getAllTranscripts approach which is more reliable for UI-created meetings.

        Args:
            video_call_data: VideoCall record data from Salesforce

        Returns:
            Dict with transcript data and metadata
        """
        try:
            from datetime import datetime, timedelta

            # Check if this is a Teams meeting
            vendor_name = video_call_data.get('VendorName', '').lower()
            if vendor_name != 'msteams':
                self.log_info(f"Skipping non-Teams meeting: {vendor_name}")
                return None

            # Extract required identifiers
            vendor_meeting_key = video_call_data.get('VendorMeetingKey')
            start_time = video_call_data.get('StartDateTime')
            end_time = video_call_data.get('EndDateTime')

            if not all([vendor_meeting_key, start_time]):
                self.log_error("Missing required Teams meeting identifiers (need VendorMeetingKey and StartDateTime)")
                return None

            # Use end_time if available, otherwise estimate 1 hour duration
            if not end_time:
                start_dt = datetime.fromisoformat(start_time.replace('+0000', '+00:00').replace('Z', '+00:00'))
                end_dt = start_dt + timedelta(hours=1)
                end_time = end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f+0000')
                self.log_warning(f"EndDateTime not provided, estimated: {end_time}")

            # Authenticate with Graph API
            if not self.authenticate():
                return None

            # Parse meeting identifiers
            parsed_keys = self.parse_vendor_meeting_key(vendor_meeting_key)
            organizer_id = parsed_keys.get('organizer_id')

            if not organizer_id:
                self.log_error("Could not extract organizer ID from meeting key")
                return None

            # Resolve organizer email for better logging
            organizer_email = self.resolve_user_email(organizer_id)
            organizer_display = organizer_email or organizer_id

            self.log_info(f"Extracting transcript for organizer: {organizer_display}")

            # Check if we have access to this organizer's meetings (lightweight pre-check)
            has_access, access_error = self.check_access_policy(organizer_id)
            if not has_access:
                self.log_error(f"Access policy check failed:\n{access_error}")
                return None

            # Get transcripts within the meeting date range
            transcripts = self.get_transcripts_by_date(organizer_id, start_time, end_time)

            if not transcripts:
                self.log_warning(f"No transcripts found for organizer {organizer_display} in date range")
                self.log_info(f"  Meeting time: {start_time} to {end_time}")
                self.log_info(f"  Possible reasons:")
                self.log_info(f"  - Transcript not enabled for this meeting")
                self.log_info(f"  - Meeting transcript still processing")
                self.log_info(f"  - Date range mismatch")
                return None

            self.transcript_stats["teams_meetings_found"] = 1

            # Match transcript by comparing start times
            meeting_start = datetime.fromisoformat(start_time.replace('+0000', '+00:00').replace('Z', '+00:00'))
            best_match = None
            min_time_diff = timedelta(days=999)

            for transcript in transcripts:
                transcript_time_str = transcript.get('createdDateTime', '')
                if transcript_time_str:
                    try:
                        transcript_time = datetime.fromisoformat(transcript_time_str.replace('Z', '+00:00'))
                        time_diff = abs(transcript_time - meeting_start)

                        if time_diff < min_time_diff:
                            min_time_diff = time_diff
                            best_match = transcript
                    except:
                        pass

            # Use best match if within 1 hour, otherwise use first transcript
            if best_match and min_time_diff < timedelta(hours=1):
                transcript = best_match
                self.log_info(f"Matched transcript by time proximity ({min_time_diff.total_seconds()/60:.1f} minutes difference)")
            else:
                transcript = transcripts[0]
                if len(transcripts) > 1:
                    self.log_warning(f"Multiple transcripts found ({len(transcripts)}), using first one")
                else:
                    self.log_info("Using the only transcript found")

            # Get content URL from transcript
            content_url = transcript.get('transcriptContentUrl')
            transcript_id = transcript.get('id')
            meeting_id = transcript.get('meetingId')

            if not content_url:
                self.log_error("Transcript object missing transcriptContentUrl")
                return None

            # Download transcript content using the provided URL
            content = self.download_transcript_content(content_url=content_url, format="text/vtt")

            if not content:
                # Try plain text format as fallback
                self.log_info("Trying plain text format...")
                content = self.download_transcript_content(content_url=content_url, format="text/plain")

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