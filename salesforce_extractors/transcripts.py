"""
Call Transcript Extractor

Handles extraction of call transcripts from Salesforce using proper Voice objects
and Connect REST API. Supports VoiceCall, VideoCall, MessagingSession, and Teams transcripts.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .base import SalesforceBase
from .teams_transcript import TeamsTranscriptExtractor


class TranscriptExtractor(SalesforceBase):
    """Extracts call transcripts and conversation data from Salesforce"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        super().__init__(org_username)
        self.voice_calls_data = []
        self.video_calls_data = []
        self.messaging_sessions_data = []
        self.transcripts_data = []
        self.teams_extractor = TeamsTranscriptExtractor(org_username)
        self.transcript_stats = {
            "voice_calls_found": 0,
            "video_calls_found": 0,
            "messaging_sessions_found": 0,
            "transcripts_extracted": 0,
            "transcripts_cleaned": 0,
            "teams_transcripts_found": 0,
            "errors": []
        }
    
    def get_voice_calls(self, related_record_id: str) -> List[Dict]:
        """
        Get VoiceCall records related to an opportunity or account
        
        Args:
            related_record_id: Opportunity or Account ID
            
        Returns:
            List of VoiceCall records
        """
        self.log_info(f"Fetching voice call records for: {related_record_id}")
        
        # Try multiple voice call objects in order of preference
        voice_call_objects = [
            {
                "object": "VoiceCall",
                "fields": "Id, Name, CallStartDateTime, CallEndDateTime, CallDurationInSeconds, CallType, CallDisposition, ConversationId, RelatedRecordId, FromPhoneNumber, ToPhoneNumber, CreatedDate, LastModifiedDate, OwnerId, Owner.Name, Description, ActivityId",
                "where_field": "RelatedRecordId"
            },
            {
                "object": "UnifiedVoiceCall", 
                "fields": "Id, Name, CallStartDateTime, CallEndDateTime, CallDurationInSeconds, CallType, CallDisposition, ConversationId, RelatedRecordId, FromPhoneNumber, ToPhoneNumber, CreatedDate, LastModifiedDate, OwnerId, Owner.Name, Description",
                "where_field": "RelatedRecordId"
            },
            {
                "object": "Voice_Call__c",
                "fields": "Id, Name, CreatedDate, LastModifiedDate, OwnerId, Owner.Name",
                "where_field": "broadvoice__Opportunity__c"
            }
        ]
        
        for voice_obj in voice_call_objects:
            query = f"""
            SELECT {voice_obj['fields']}
            FROM {voice_obj['object']}
            WHERE {voice_obj['where_field']} = '{related_record_id}'
            ORDER BY CreatedDate DESC
            LIMIT 50
            """
            
            self.log_info(f"Trying {voice_obj['object']} object...")
            # Use log_errors=False for fallback queries to avoid cluttering logs
            result = self.run_soql_query(query, log_errors=False)
            
            if result and result.get("totalSize", 0) > 0:
                self.voice_calls_data = result["records"]
                self.transcript_stats["voice_calls_found"] = len(self.voice_calls_data)
                self.log_success(f"Found {len(self.voice_calls_data)} voice calls in {voice_obj['object']}")
                return self.voice_calls_data
        
        self.log_info("No voice calls found in any available objects")
        return []
    
    def get_voice_calls_by_account(self, account_id: str) -> List[Dict]:
        """
        Get VoiceCall records by searching related tasks/events on the account

        Args:
            account_id: Account ID

        Returns:
            List of VoiceCall records
        """
        self.log_info(f"Fetching voice calls by account: {account_id}")

        # First, get tasks with CallObject field
        # Note: Can't use semi-join with Task object, so we do this in two steps
        tasks_query = f"""
        SELECT Id, CallObject
        FROM Task
        WHERE WhatId = '{account_id}' AND CallObject != null
        LIMIT 100
        """

        tasks_result = self.run_soql_query(tasks_query, log_errors=False)
        if not tasks_result or tasks_result.get("totalSize", 0) == 0:
            self.log_info("No tasks with call objects found")
            return []

        # Extract CallObject IDs
        call_object_ids = [task["CallObject"] for task in tasks_result["records"] if task.get("CallObject")]

        if not call_object_ids:
            self.log_info("No call object IDs found in tasks")
            return []

        # Now query VoiceCall records directly with the IDs
        # Use batching for large ID lists (Salesforce SOQL has limits)
        call_ids_str = "', '".join(call_object_ids)
        voice_calls_query = f"""
        SELECT Id, Name, CallStartDateTime, CallEndDateTime, CallDurationInSeconds,
               CallType, CallDisposition, RelatedRecordId,
               FromPhoneNumber, ToPhoneNumber, CreatedDate
        FROM VoiceCall
        WHERE Id IN ('{call_ids_str}')
        ORDER BY CallStartDateTime DESC
        """

        result = self.run_soql_query(voice_calls_query)
        if result and result.get("totalSize", 0) > 0:
            calls = result["records"]
            self.log_success(f"Found {len(calls)} voice calls via account tasks")
            return calls

        self.log_info("No voice calls found via account")
        return []
    
    def get_conversation_identifier(self, conversation_id: str) -> Optional[str]:
        """
        Get ConversationIdentifier from Conversation object
        
        Args:
            conversation_id: Conversation ID from VoiceCall
            
        Returns:
            ConversationIdentifier for Connect API or None
        """
        if not conversation_id:
            return None
        
        self.log_info(f"Getting ConversationIdentifier for: {conversation_id}")
        
        query = f"""
        SELECT Id, ConversationIdentifier, CreatedDate
        FROM Conversation 
        WHERE Id = '{conversation_id}'
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            conversation_identifier = result["records"][0].get("ConversationIdentifier")
            if conversation_identifier:
                self.log_success(f"Found ConversationIdentifier: {conversation_identifier}")
                return conversation_identifier
        
        self.log_warning(f"No ConversationIdentifier found for: {conversation_id}")
        return None
    
    def get_conversation_entries(self, conversation_identifier: str) -> Optional[List[Dict]]:
        """
        Get conversation entries using Connect REST API
        
        Args:
            conversation_identifier: Conversation identifier from Conversation object
            
        Returns:
            List of conversation entries or None if failed
        """
        if not conversation_identifier:
            return None
        
        self.log_info(f"Fetching conversation entries for: {conversation_identifier}")
        
        try:
            # Use Connect REST API endpoint
            endpoint = f"/services/data/v64.0/connect/conversation/{conversation_identifier}/entries"
            response = self.run_api_request(endpoint, method="GET")
            
            if response:
                # Parse JSON response
                data = json.loads(response.decode('utf-8'))
                
                if "entries" in data:
                    entries = data["entries"]
                    self.log_success(f"Found {len(entries)} conversation entries")
                    return entries
                else:
                    self.log_warning("No entries found in conversation response")
                    return []
            
            self.log_error(f"Failed to get conversation entries for: {conversation_identifier}")
            return None
            
        except Exception as e:
            error_msg = f"Error getting conversation entries: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
            return None
    
    def get_video_calls(self, related_record_id: str, opportunity_name: str = None) -> List[Dict]:
        """
        Get VideoCall records related to an opportunity or account

        Args:
            related_record_id: Opportunity or Account ID
            opportunity_name: Optional opportunity name for name-based search

        Returns:
            List of VideoCall records
        """
        self.log_info(f"Fetching video call records for: {related_record_id}")

        # Try to find VideoCall records by RelatedRecordId
        query = f"""
        SELECT Id, Name, StartDateTime, EndDateTime, DurationInSeconds,
               VendorName, VendorMeetingUuid, VendorMeetingKey, ExternalId,
               RelatedRecordId, IsRecorded, IsDiarizationOptIn, TranscribedLanguage,
               IntelligenceScore, MeetingType, HostId, CreatedDate
        FROM VideoCall
        WHERE RelatedRecordId = '{related_record_id}'
        ORDER BY StartDateTime DESC
        """

        result = self.run_soql_query(query, log_errors=False)
        if result and result.get("totalSize", 0) > 0:
            video_calls = result["records"]
            self.log_success(f"Found {len(video_calls)} video calls via RelatedRecordId")
            self.video_calls_data = video_calls
            self.transcript_stats["video_calls_found"] = len(video_calls)
            return video_calls

        # Try searching by opportunity ID in the name (common naming pattern)
        if related_record_id.startswith('006'):  # Opportunity ID prefix
            self.log_info(f"Trying VideoCall search by name pattern containing opportunity ID")
            name_query = f"""
            SELECT Id, Name, StartDateTime, EndDateTime, DurationInSeconds,
                   VendorName, VendorMeetingUuid, VendorMeetingKey, ExternalId,
                   RelatedRecordId, IsRecorded, IsDiarizationOptIn, TranscribedLanguage,
                   IntelligenceScore, MeetingType, HostId, CreatedDate
            FROM VideoCall
            WHERE Name LIKE '%{related_record_id}%'
            ORDER BY StartDateTime DESC
            LIMIT 10
            """

            result = self.run_soql_query(name_query, log_errors=False)
            if result and result.get("totalSize", 0) > 0:
                video_calls = result["records"]
                self.log_success(f"Found {len(video_calls)} video calls via name search with opportunity ID")
                self.video_calls_data = video_calls
                self.transcript_stats["video_calls_found"] = len(video_calls)
                return video_calls

        # Try searching by opportunity name pattern if provided
        if opportunity_name:
            # Extract key words from opportunity name (remove common words)
            name_parts = opportunity_name.replace('-', ' ').split()
            # Use first significant word (>3 chars) for search
            search_terms = [part for part in name_parts if len(part) > 3]

            if search_terms:
                search_term = search_terms[0][:20]  # Limit length for SOQL
                self.log_info(f"Trying VideoCall search by name pattern containing '{search_term}'")
                name_query = f"""
                SELECT Id, Name, StartDateTime, EndDateTime, DurationInSeconds,
                       VendorName, VendorMeetingUuid, VendorMeetingKey, ExternalId,
                       RelatedRecordId, IsRecorded, IsDiarizationOptIn, TranscribedLanguage,
                       IntelligenceScore, MeetingType, HostId, CreatedDate
                FROM VideoCall
                WHERE Name LIKE '%{search_term}%'
                ORDER BY StartDateTime DESC
                LIMIT 10
                """

                result = self.run_soql_query(name_query, log_errors=False)
                if result and result.get("totalSize", 0) > 0:
                    video_calls = result["records"]
                    self.log_success(f"Found {len(video_calls)} video calls via name search")
                    self.video_calls_data = video_calls
                    self.transcript_stats["video_calls_found"] = len(video_calls)
                    return video_calls

        self.log_info("No video calls found")
        return []
    
    def get_video_call_recordings(self, video_call_id: str) -> List[Dict]:
        """
        Get VideoCallRecording records for transcripts and recordings
        
        Args:
            video_call_id: VideoCall ID
            
        Returns:
            List of VideoCallRecording records
        """
        self.log_info(f"Fetching video call recordings for: {video_call_id}")
        
        query = f"""
        SELECT Id, Name, VideoCallRecordId, FileType, StartDateTime, EndDateTime,
               DurationInSeconds, FileSizeInByte, ExternalRecordingKey,
               ExternalRecordingKeyLong, CreatedDate
        FROM VideoCallRecording
        WHERE VideoCallRecordId = '{video_call_id}'
        ORDER BY StartDateTime DESC
        """
        
        result = self.run_soql_query(query)
        if result and result.get("totalSize", 0) > 0:
            recordings = result["records"]
            self.log_success(f"Found {len(recordings)} video call recordings")
            
            # Log file types found
            file_types = [r.get('FileType') for r in recordings]
            self.log_info(f"Recording types: {', '.join(set(file_types))}")
            
            return recordings
        
        self.log_info("No video call recordings found")
        return []
    
    def extract_teams_transcript(self, video_call: Dict, output_dir: Path) -> Optional[Dict]:
        """
        Extract Teams meeting transcript for a VideoCall
        
        Args:
            video_call: VideoCall record data
            output_dir: Directory to save transcript
            
        Returns:
            Teams transcript data if successful
        """
        if video_call.get('VendorName', '').lower() != 'msteams':
            return None
        
        self.log_info(f"Extracting Teams transcript for: {video_call.get('Name', 'Unknown')}")
        
        try:
            # Use TeamsTranscriptExtractor to get transcript
            transcript_data = self.teams_extractor.extract_teams_transcript(video_call)
            
            if transcript_data:
                # Save transcript to file
                video_call_id = video_call.get('Id', 'unknown')
                transcript_path = output_dir / f"teams_transcript_{video_call_id}"
                
                if self.teams_extractor.save_transcript(transcript_data, str(transcript_path)):
                    self.transcript_stats["teams_transcripts_found"] += 1
                    self.transcript_stats["transcripts_extracted"] += 1
                    
                    return {
                        "source": "teams",
                        "video_call_id": video_call_id,
                        "transcript_path": f"{transcript_path}.txt",
                        "metadata_path": f"{transcript_path}_metadata.json",
                        "content_length": len(transcript_data.get('content', '')),
                        "format": transcript_data.get('format', 'unknown')
                    }
            
            return None
            
        except Exception as e:
            error_msg = f"Error extracting Teams transcript: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
            return None
    
    def get_messaging_sessions(self, account_id: str) -> List[Dict]:
        """
        Get MessagingSession records for chat transcripts
        
        Args:
            account_id: Account ID
            
        Returns:
            List of MessagingSession records
        """
        self.log_info(f"Fetching messaging sessions for account: {account_id}")
        
        # Try multiple messaging/chat objects
        messaging_queries = [
            {
                "name": "MessagingSession via Cases",
                "query": f"""
                SELECT Id, Name, StartTime, EndTime, ConversationId,
                       Conversation.ConversationIdentifier, Status, Channel,
                       CaseId, Case.CaseNumber, CreatedDate
                FROM MessagingSession
                WHERE CaseId IN (SELECT Id FROM Case WHERE AccountId = '{account_id}')
                ORDER BY StartTime DESC
                LIMIT 50
                """
            },
            {
                "name": "MessagingSession direct",
                "query": f"""
                SELECT Id, Name, StartTime, EndTime, ConversationId, Status, Channel, CreatedDate
                FROM MessagingSession
                ORDER BY StartTime DESC
                LIMIT 50
                """
            },
            {
                "name": "LiveChatTranscript",
                "query": f"""
                SELECT Id, Name, StartTime, EndTime, Status, CreatedDate, Body
                FROM LiveChatTranscript
                WHERE Case.AccountId = '{account_id}'
                ORDER BY StartTime DESC
                LIMIT 50
                """
            }
        ]
        
        for query_info in messaging_queries:
            self.log_info(f"Trying {query_info['name']}...")
            result = self.run_soql_query(query_info["query"], log_errors=False)
            
            if result and result.get("totalSize", 0) > 0:
                self.messaging_sessions_data = result["records"]
                self.transcript_stats["messaging_sessions_found"] = len(self.messaging_sessions_data)
                self.log_success(f"Found {len(self.messaging_sessions_data)} messaging sessions via {query_info['name']}")
                return self.messaging_sessions_data
        
        self.log_info("No messaging sessions found in any available objects")
        return []
    
    def extract_transcript_from_entries(self, entries: List[Dict], metadata: Dict) -> Dict:
        """
        Extract and format transcript from conversation entries
        
        Args:
            entries: List of conversation entries
            metadata: Call metadata (call info, participants, etc.)
            
        Returns:
            Formatted transcript dictionary
        """
        if not entries:
            return {}
        
        transcript_lines = []
        participants = set()
        
        for entry in entries:
            # Extract entry details
            entry_time = entry.get("entryTime", "")
            actor_name = entry.get("actorName", "Unknown")
            actor_type = entry.get("actorType", "")
            message = entry.get("message", "")
            entry_type = entry.get("entryType", "")
            
            # Track participants
            if actor_name and actor_name != "Unknown":
                participants.add(actor_name)
            
            # Format based on entry type
            if entry_type == "Message" and message:
                timestamp = entry_time[:19] if entry_time else ""
                transcript_lines.append(f"[{timestamp}] {actor_name}: {message}")
            
            elif entry_type == "SystemMessage" and message:
                timestamp = entry_time[:19] if entry_time else ""
                transcript_lines.append(f"[{timestamp}] SYSTEM: {message}")
        
        return {
            "transcript_text": "\n".join(transcript_lines),
            "participants": list(participants),
            "total_entries": len(entries),
            "message_entries": len([e for e in entries if e.get("entryType") == "Message"]),
            "metadata": metadata,
            "raw_entries": entries
        }
    
    def get_einstein_insights(self, voice_call_ids: List[str]) -> List[Dict]:
        """
        Get Einstein Conversation Insights data
        
        Args:
            voice_call_ids: List of VoiceCall IDs
            
        Returns:
            List of insights records
        """
        if not voice_call_ids:
            return []
        
        self.log_info("Fetching conversation insights and call coaching data")
        
        # Check for Einstein Call Coaching objects first - these are more likely to exist
        coaching_queries = [
            {
                "name": "CallCoachingMediaProvider",
                "query": f"""
                SELECT Id, Name, CreatedDate, LastModifiedDate
                FROM CallCoachingMediaProvider
                LIMIT 10
                """
            },
            {
                "name": "VoiceCallRecording", 
                "query": f"""
                SELECT Id, Name, CallId, CreatedDate, LastModifiedDate
                FROM VoiceCallRecording
                WHERE CallId IN ('{"', '".join(voice_call_ids)}')
                ORDER BY CreatedDate DESC
                LIMIT 50
                """
            }
        ]
        
        all_insights = []
        
        for query_info in coaching_queries:
            self.log_info(f"Trying {query_info['name']}...")
            result = self.run_soql_query(query_info["query"], log_errors=False)
            
            if result and result.get("totalSize", 0) > 0:
                insights = result["records"]
                all_insights.extend(insights)
                self.log_success(f"Found {len(insights)} records in {query_info['name']}")
        
        if not all_insights:
            self.log_info("No conversation insights or call recordings found")
        
        return all_insights
    
    def extract_task_call_descriptions(self, opportunity_id: str, account_id: str) -> List[Dict]:
        """
        Extract call information from Task descriptions
        
        Args:
            opportunity_id: Opportunity ID
            account_id: Account ID
            
        Returns:
            List of tasks with call information
        """
        self.log_info("Extracting call info from task descriptions")
        
        query = f"""
        SELECT Id, Subject, Status, ActivityDate, Description,
               WhoId, Who.Name, WhatId, What.Name, OwnerId, Owner.Name,
               CreatedDate, Type, CallType, CallDurationInSeconds
        FROM Task
        WHERE (WhatId = '{opportunity_id}' OR WhatId = '{account_id}')
        AND (Subject LIKE '%call%' OR Type = 'Call' OR CallType != null)
        ORDER BY ActivityDate DESC
        """
        
        result = self.run_soql_query(query)
        call_tasks = []
        
        if result and result.get("totalSize", 0) > 0:
            tasks = result["records"]
            
            for task in tasks:
                description = task.get("Description", "")
                subject = task.get("Subject", "")
                
                # Look for transcript-like content in description
                if description and len(description) > 200:
                    # This might be a transcript
                    call_tasks.append({
                        "type": "task_transcript",
                        "task_id": task["Id"],
                        "subject": subject,
                        "date": task.get("ActivityDate"),
                        "description": description,
                        "call_duration": task.get("CallDurationInSeconds"),
                        "owner": task.get("Owner", {}).get("Name"),
                        "contact": task.get("Who", {}).get("Name")
                    })
            
            if call_tasks:
                self.log_success(f"Found {len(call_tasks)} tasks with potential transcripts")
        
        return call_tasks
    
    def save_transcript(self, transcript_data: Dict, output_dir: Path, filename: str):
        """
        Save transcript to file
        
        Args:
            transcript_data: Transcript data dictionary
            output_dir: Output directory
            filename: Output filename
        """
        try:
            raw_dir = output_dir / "transcripts" / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = raw_dir / filename
            
            # Create formatted transcript
            content_lines = []
            
            # Add metadata header
            metadata = transcript_data.get("metadata", {})
            if metadata:
                content_lines.append("=" * 60)
                content_lines.append("CALL TRANSCRIPT")
                content_lines.append("=" * 60)
                
                for key, value in metadata.items():
                    if value:
                        content_lines.append(f"{key}: {value}")
                
                content_lines.append("")
                content_lines.append("PARTICIPANTS:")
                for participant in transcript_data.get("participants", []):
                    content_lines.append(f"- {participant}")
                
                content_lines.append("")
                content_lines.append("TRANSCRIPT:")
                content_lines.append("-" * 40)
                content_lines.append("")
            
            # Add transcript text
            transcript_text = transcript_data.get("transcript_text", "")
            if transcript_text:
                content_lines.append(transcript_text)
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(content_lines))
            
            self.log_success(f"Saved transcript: {filename}")
            self.transcript_stats["transcripts_extracted"] += 1
            
        except Exception as e:
            error_msg = f"Failed to save transcript {filename}: {str(e)}"
            self.log_error(error_msg)
            self.transcript_stats["errors"].append(error_msg)
    
    def clean_transcripts(self, output_dir: Path):
        """
        Clean transcripts using existing cleanup_transcript.py script
        
        Args:
            output_dir: Output directory containing transcripts
        """
        cleanup_script = Path("cleanup_transcript.py")
        if not cleanup_script.exists():
            self.log_warning("cleanup_transcript.py not found, skipping transcript cleaning")
            return
        
        raw_dir = output_dir / "transcripts" / "raw"
        cleaned_dir = output_dir / "transcripts" / "cleaned"
        cleaned_dir.mkdir(parents=True, exist_ok=True)
        
        if not raw_dir.exists():
            return
        
        self.log_info("Cleaning transcripts...")
        
        for raw_file in raw_dir.glob("*.txt"):
            try:
                cleaned_name = raw_file.stem + "_cleaned.txt"
                cleaned_path = cleaned_dir / cleaned_name
                
                cmd = ["python", str(cleanup_script), str(raw_file), str(cleaned_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    self.log_success(f"Cleaned: {raw_file.name}")
                    self.transcript_stats["transcripts_cleaned"] += 1
                else:
                    self.log_warning(f"Could not clean: {raw_file.name}")
                    
            except Exception as e:
                self.log_error(f"Error cleaning {raw_file.name}: {str(e)}")
    
    def extract_all_transcripts(self, opportunity_id: str, account_id: str, output_dir: Path, opportunity_name: str = None) -> Dict:
        """
        Extract all transcripts from various sources

        Args:
            opportunity_id: Opportunity ID
            account_id: Account ID
            output_dir: Output directory
            opportunity_name: Optional opportunity name for name-based VideoCall search

        Returns:
            Extraction results and statistics
        """
        self.log_info("Starting comprehensive transcript extraction")

        # Reset stats
        self.transcript_stats = {
            "voice_calls_found": 0,
            "video_calls_found": 0,
            "messaging_sessions_found": 0,
            "transcripts_extracted": 0,
            "transcripts_cleaned": 0,
            "teams_transcripts_found": 0,
            "errors": []
        }

        all_transcripts = []

        # 1. Extract VoiceCall transcripts
        voice_calls = self.get_voice_calls(opportunity_id)
        if not voice_calls:
            # Try finding by account
            voice_calls = self.get_voice_calls_by_account(account_id)

        for i, call in enumerate(voice_calls, 1):
            conversation_id = call.get("ConversationId")
            if conversation_id:
                conversation_identifier = self.get_conversation_identifier(conversation_id)
                if conversation_identifier:
                    entries = self.get_conversation_entries(conversation_identifier)
                    if entries:
                        # Create metadata
                        metadata = {
                            "call_id": call["Id"],
                            "call_start": call.get("CallStartDateTime"),
                            "call_end": call.get("CallEndDateTime"),
                            "duration": call.get("CallDurationInSeconds"),
                            "from_number": call.get("FromPhoneNumber"),
                            "to_number": call.get("ToPhoneNumber"),
                            "call_type": call.get("CallType"),
                            "disposition": call.get("CallDisposition")
                        }

                        transcript_data = self.extract_transcript_from_entries(entries, metadata)
                        filename = f"voicecall_transcript_{i}_{call.get('CallStartDateTime', '')[:10]}.txt"
                        self.save_transcript(transcript_data, output_dir, filename)
                        all_transcripts.append(transcript_data)

        # 2. Extract VideoCall transcripts (Teams/WebEx/Zoom)
        video_calls = self.get_video_calls(opportunity_id, opportunity_name)
        for video_call in video_calls:
            video_call_id = video_call.get('Id')
            
            # Get video call recordings to check for transcripts
            recordings = self.get_video_call_recordings(video_call_id)
            
            # Check for Teams transcripts
            if video_call.get('VendorName', '').lower() == 'msteams':
                teams_transcript = self.extract_teams_transcript(video_call, output_dir)
                if teams_transcript:
                    all_transcripts.append(teams_transcript)
                    continue  # Teams transcript found, skip other methods
            
            # Log VideoCallRecording info for potential future extraction
            transcript_recordings = [r for r in recordings if r.get('FileType') == 'TRANSCRIPT']
            if transcript_recordings:
                self.log_info(f"Found {len(transcript_recordings)} transcript recordings (extraction not yet implemented)")
                # Future: Implement direct VideoCallRecording content extraction
        
        # 3. Extract MessagingSession transcripts
        messaging_sessions = self.get_messaging_sessions(account_id)
        for i, session in enumerate(messaging_sessions, 1):
            conversation_identifier = session.get("Conversation", {}).get("ConversationIdentifier")
            if conversation_identifier:
                entries = self.get_conversation_entries(conversation_identifier)
                if entries:
                    metadata = {
                        "session_id": session["Id"],
                        "start_time": session.get("StartTime"),
                        "end_time": session.get("EndTime"),
                        "channel": session.get("Channel"),
                        "case_number": session.get("Case", {}).get("CaseNumber")
                    }
                    
                    transcript_data = self.extract_transcript_from_entries(entries, metadata)
                    filename = f"messaging_transcript_{i}_{session.get('StartTime', '')[:10]}.txt"
                    self.save_transcript(transcript_data, output_dir, filename)
                    all_transcripts.append(transcript_data)
        
        # 4. Extract Task call descriptions
        call_tasks = self.extract_task_call_descriptions(opportunity_id, account_id)
        for i, task in enumerate(call_tasks, 1):
            if task["description"]:
                metadata = {
                    "task_id": task["task_id"],
                    "subject": task["subject"],
                    "date": task["date"],
                    "owner": task["owner"],
                    "contact": task["contact"]
                }
                
                transcript_data = {
                    "transcript_text": task["description"],
                    "participants": [task["owner"], task["contact"]],
                    "metadata": metadata
                }
                
                filename = f"task_transcript_{i}_{task.get('date', 'unknown')}.txt"
                self.save_transcript(transcript_data, output_dir, filename)
                all_transcripts.append(transcript_data)
        
        # 5. Clean transcripts
        self.clean_transcripts(output_dir)
        
        # 6. Get Einstein insights
        voice_call_ids = [call["Id"] for call in voice_calls]
        insights = self.get_einstein_insights(voice_call_ids)
        
        results = {
            "transcripts": all_transcripts,
            "voice_calls": voice_calls,
            "video_calls": video_calls,
            "messaging_sessions": messaging_sessions,
            "insights": insights,
            "stats": self.transcript_stats,
            "extraction_stats": self.get_extraction_stats()
        }
        
        total_extracted = self.transcript_stats["transcripts_extracted"]
        total_cleaned = self.transcript_stats["transcripts_cleaned"]
        
        if total_extracted > 0:
            self.log_success(f"Transcript extraction complete: {total_extracted} extracted, {total_cleaned} cleaned")
        else:
            self.log_info("No transcripts found or extracted")
        
        return results
    
    def get_current_voice_calls(self) -> List[Dict]:
        """Get currently loaded voice calls"""
        return self.voice_calls_data
    
    def get_current_transcripts(self) -> List[Dict]:
        """Get currently loaded transcripts"""
        return self.transcripts_data
    
    def get_transcript_stats(self) -> Dict:
        """Get transcript extraction statistics"""
        return self.transcript_stats.copy()