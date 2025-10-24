"""
Base Salesforce Extractor

Provides core functionality for all Salesforce data extractors including:
- SOQL query execution via SF CLI
- REST API requests
- Session management
- Error handling
"""

import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


class SalesforceBase:
    """Base class for all Salesforce extractors with common functionality"""
    
    def __init__(self, org_username: str = "jcamarate@broadvoice.com"):
        """
        Initialize base Salesforce extractor
        
        Args:
            org_username: Salesforce org username/alias
        """
        self.org = org_username
        self.extraction_stats = {
            "start_time": datetime.now().isoformat(),
            "queries_executed": 0,
            "api_requests": 0,
            "errors": []
        }
        
        # Verify SF CLI connection
        if not self._verify_org_connection():
            raise ConnectionError(f"Cannot connect to Salesforce org: {org_username}")
    
    def _verify_org_connection(self) -> bool:
        """Verify connection to Salesforce org"""
        try:
            cmd = ["sf", "org", "display", "--target-org", self.org, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                org_info = json.loads(result.stdout)
                return org_info.get("result", {}).get("connectedStatus") == "Connected"
            return False
        except Exception:
            return False
    
    def run_soql_query(self, query: str, log_errors: bool = True) -> Optional[Dict]:
        """
        Execute SOQL query via SF CLI
        
        Args:
            query: SOQL query string
            log_errors: Whether to log errors (useful for fallback scenarios)
            
        Returns:
            Query result dictionary or None if failed
        """
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
    
    def run_api_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None, output_file: Optional[str] = None) -> Optional[bytes]:
        """
        Execute REST API request via SF CLI
        
        Args:
            endpoint: API endpoint path (e.g., "/services/data/v64.0/...")
            method: HTTP method (GET, POST, PUT, DELETE)
            data: Request body data for POST/PUT requests
            output_file: Optional file path to stream binary response directly to file
            
        Returns:
            Response bytes or None if failed (None when output_file is specified)
        """
        try:
            # Remove leading slash if present since sf api request rest expects the endpoint without it
            clean_endpoint = endpoint.lstrip('/')
            
            cmd = [
                "sf", "api", "request", "rest",
                clean_endpoint,
                "--method", method,
                "--target-org", self.org
            ]
            
            if data:
                cmd.extend(["--body", json.dumps(data)])
            
            # Use --stream-to-file for binary downloads
            if output_file:
                cmd.extend(["--stream-to-file", output_file])
            
            result = subprocess.run(cmd, capture_output=True, check=False)
            self.extraction_stats["api_requests"] += 1
            
            if result.returncode == 0:
                if output_file:
                    # For file streaming, we don't return bytes but indicate success
                    return b""  # Empty bytes to indicate success
                else:
                    return result.stdout
            else:
                error_msg = f"API request failed: {result.stderr.decode() if result.stderr else 'Unknown error'}"
                self.extraction_stats["errors"].append(error_msg)
                print(f"❌ {error_msg}")
                return None
                
        except Exception as e:
            error_msg = f"API request exception: {str(e)}"
            self.extraction_stats["errors"].append(error_msg)
            print(f"❌ {error_msg}")
            return None
    
    def get_org_info(self) -> Optional[Dict]:
        """
        Get Salesforce org information
        
        Returns:
            Org info dictionary with instanceUrl, accessToken, etc.
        """
        try:
            cmd = ["sf", "org", "display", "--target-org", self.org, "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                org_data = json.loads(result.stdout)
                return org_data.get("result")
            return None
            
        except Exception as e:
            error_msg = f"Failed to get org info: {str(e)}"
            self.extraction_stats["errors"].append(error_msg)
            return None
    
    def get_session_info(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get session info for direct API calls
        
        Returns:
            Tuple of (instance_url, access_token) or (None, None) if failed
        """
        org_info = self.get_org_info()
        if org_info:
            instance_url = org_info.get("instanceUrl")
            access_token = org_info.get("accessToken")
            return instance_url, access_token
        return None, None
    
    def run_curl_request(self, endpoint: str, output_file: str = None, method: str = "GET") -> bool:
        """
        Execute cURL request with OAuth token (fallback method)
        
        Args:
            endpoint: API endpoint path
            output_file: Optional file path to save response
            method: HTTP method
            
        Returns:
            True if successful, False otherwise
        """
        try:
            instance_url, access_token = self.get_session_info()
            if not instance_url or not access_token:
                return False
            
            curl_cmd = [
                "curl",
                "-H", f"Authorization: Bearer {access_token}",
                "-X", method
            ]
            
            if output_file:
                curl_cmd.extend(["-o", output_file])
            
            curl_cmd.append(f"{instance_url}{endpoint}")
            
            result = subprocess.run(curl_cmd, capture_output=True, check=False)
            self.extraction_stats["api_requests"] += 1
            
            return result.returncode == 0
            
        except Exception as e:
            error_msg = f"cURL request failed: {str(e)}"
            self.extraction_stats["errors"].append(error_msg)
            return False
    
    def log_error(self, error_message: str):
        """Log an error to the extraction stats"""
        self.extraction_stats["errors"].append(error_message)
        print(f"❌ {error_message}")
    
    def log_info(self, message: str):
        """Log an info message"""
        print(f"ℹ️  {message}")
    
    def log_success(self, message: str):
        """Log a success message"""
        print(f"✅ {message}")
    
    def log_warning(self, message: str):
        """Log a warning message"""
        print(f"⚠️  {message}")
    
    def get_extraction_stats(self) -> Dict:
        """Get current extraction statistics"""
        stats = self.extraction_stats.copy()
        stats["duration_seconds"] = (
            datetime.now() - datetime.fromisoformat(stats["start_time"])
        ).total_seconds()
        return stats
    
    def reset_stats(self):
        """Reset extraction statistics"""
        self.extraction_stats = {
            "start_time": datetime.now().isoformat(),
            "queries_executed": 0,
            "api_requests": 0,
            "errors": []
        }