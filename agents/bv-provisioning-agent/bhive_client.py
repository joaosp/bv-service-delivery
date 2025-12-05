"""
SSE client for b-hive MCP server

This module provides an SSE client to communicate with the b-hive provisioning
MCP server using JSON-RPC over Server-Sent Events (SSE).

MCP SSE Protocol:
1. Connect to /mcp/sse endpoint
2. Server sends 'endpoint' event with session-specific messages URL
3. POST JSON-RPC requests to that session URL
4. Responses arrive via the SSE stream
"""
import httpx
import json
import asyncio
from typing import Dict, Any, Optional, Tuple
from config import BHIVE_MCP_SERVER_URL, BHIVE_MCP_TIMEOUT
from cancellation import CancellationRequestedError


class BHiveMCPClient:
    """
    SSE client for b-hive MCP server.

    Communicates with the MCP server via JSON-RPC over SSE to provision
    b-hive UCaaS accounts, locations, users, and phone numbers.
    """

    def __init__(self, base_url: str = None):
        """
        Initialize the MCP client.

        Args:
            base_url: Base URL of the MCP server. Defaults to BHIVE_MCP_SERVER_URL from config.
        """
        self.base_url = base_url or BHIVE_MCP_SERVER_URL
        self.sse_url = f"{self.base_url}/mcp/sse"
        self._request_id = 0

    def _next_request_id(self) -> int:
        """Generate a unique request ID for JSON-RPC"""
        self._request_id += 1
        return self._request_id

    def _parse_sse_event(self, event_str: str) -> Tuple[Optional[str], Optional[Any]]:
        """
        Parse an SSE event string. Skips SSE comments (lines starting with ':').

        Returns:
            Tuple of (event_type, data) where data is parsed JSON if possible
        """
        event_type = None
        data = None

        for line in event_str.split("\n"):
            line = line.strip()
            # Skip SSE comments (lines starting with ':')
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str:
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        data = data_str  # Keep as string (like endpoint URL)

        return event_type, data

    def _parse_mcp_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse MCP tool response to extract the actual content.

        MCP responses are formatted as:
        {"content": [{"type": "text", "text": "{\"status\":\"success\",...}"}], "isError": bool}

        This method extracts and parses the JSON from content[0].text.

        Args:
            result: Raw result from call_tool() - the JSON-RPC response

        Returns:
            Parsed dictionary from the text content, or error dict if parsing fails
        """
        mcp_result = result.get("result", {})

        # Check for MCP error flag
        if mcp_result.get("isError"):
            content = mcp_result.get("content", [])
            error_text = content[0].get("text", "Unknown error") if content else "Unknown error"
            return {"success": False, "error": error_text}

        # Extract content from array
        content = mcp_result.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            first_content = content[0]
            if isinstance(first_content, dict) and first_content.get("type") == "text":
                text = first_content.get("text", "")
                # Parse JSON from text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # If not valid JSON, return as raw text
                    return {"success": False, "error": f"Invalid JSON in response: {text[:200]}"}

        # Fallback - return as-is if not in expected format
        return mcp_result

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        max_retries: int = 3,
        cancel_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Call an MCP tool with retry logic for SSE connection issues.

        Args:
            tool_name: Name of the MCP tool to call (e.g., "provision_complete_customer")
            arguments: Dictionary of arguments to pass to the tool
            max_retries: Maximum number of retry attempts (default: 3)
            cancel_event: Optional asyncio.Event for cancellation support.
                         If set, the operation will be cancelled.

        Returns:
            Dictionary containing the tool's response

        Raises:
            httpx.HTTPStatusError: If all retry attempts fail
            CancellationRequestedError: If the operation was cancelled
            Exception: If the JSON-RPC response contains an error
        """
        last_exception = None

        for attempt in range(max_retries):
            # Check for cancellation before each attempt
            if cancel_event and cancel_event.is_set():
                raise CancellationRequestedError("Operation cancelled by user before attempt")

            try:
                return await self._call_tool_impl(tool_name, arguments, cancel_event)
            except CancellationRequestedError:
                # Don't retry on cancellation
                raise
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadError) as e:
                last_exception = e
                print(f"[BHiveMCPClient] SSE connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = 1 * (attempt + 1)  # 1s, 2s, 3s exponential backoff
                    print(f"[BHiveMCPClient] Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                # For unexpected errors, don't retry
                print(f"[BHiveMCPClient] Unexpected error: {e}")
                raise

        print(f"[BHiveMCPClient] All {max_retries} attempts failed")
        raise last_exception

    async def _call_tool_impl(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        cancel_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Internal implementation: Call an MCP tool via JSON-RPC over SSE.

        MCP SSE Protocol flow:
        1. Connect to /mcp/sse
        2. Wait for 'endpoint' event with session URL
        3. POST request to session URL
        4. Wait for response on SSE stream

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Dictionary of arguments to pass to the tool
            cancel_event: Optional asyncio.Event for cancellation support

        Returns:
            Dictionary containing the tool's response

        Raises:
            httpx.HTTPStatusError: If the HTTP request fails
            CancellationRequestedError: If the operation was cancelled
            Exception: If the JSON-RPC response contains an error
        """
        request_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        result = None
        messages_url = None  # Don't set default - wait for endpoint event

        async with httpx.AsyncClient(timeout=httpx.Timeout(BHIVE_MCP_TIMEOUT, connect=10.0)) as client:
            # Connect to SSE endpoint
            async with client.stream("GET", self.sse_url, headers={"Accept": "text/event-stream"}) as sse_response:
                sse_response.raise_for_status()

                buffer = ""
                request_sent = False

                async for chunk in sse_response.aiter_text():
                    # Check for cancellation before processing each chunk
                    if cancel_event and cancel_event.is_set():
                        print("[BHiveMCPClient] Cancellation requested during SSE stream")
                        raise CancellationRequestedError("Operation cancelled by user during SSE stream")

                    buffer += chunk

                    # Parse SSE events (delimited by double newlines)
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)

                        # Skip empty events
                        if not event_str.strip():
                            continue

                        event_type, event_data = self._parse_sse_event(event_str)

                        # WAIT for endpoint event to get session URL
                        if event_type == "endpoint" and event_data:
                            messages_url = event_data
                            if not messages_url.startswith("http"):
                                messages_url = f"{self.base_url}{messages_url}"
                            print(f"[BHiveMCPClient] Got session URL: {messages_url}")

                            # NOW send the request (only after getting endpoint)
                            if not request_sent:
                                print(f"[BHiveMCPClient] Sending request to {messages_url}")
                                post_response = await client.post(
                                    messages_url,
                                    json=payload,
                                    headers={"Content-Type": "application/json"}
                                )
                                print(f"[BHiveMCPClient] POST status: {post_response.status_code}")
                                request_sent = True

                        # Look for response AFTER we sent the request
                        elif request_sent and isinstance(event_data, dict):
                            print(f"[BHiveMCPClient] Got dict response: {list(event_data.keys())}")

                            # Check if this is our JSON-RPC response
                            if event_data.get("id") == request_id:
                                result = event_data
                                print(f"[BHiveMCPClient] Got response for request {request_id}")
                                break
                            # Check for jsonrpc response format
                            if event_data.get("jsonrpc") == "2.0":
                                result = event_data
                                print(f"[BHiveMCPClient] Got JSON-RPC result")
                                break

                    if result:
                        break

        if result is None:
            raise Exception("No response received from MCP server")

        # Log actual error if present
        if "error" in result:
            error = result["error"]
            print(f"[BHiveMCPClient] Error response: {error}")
            raise Exception(f"MCP Error ({error.get('code', 'unknown')}): {error.get('message', 'Unknown error')}")

        return result

    def check_health_sync(self) -> Dict[str, Any]:
        """
        Synchronous health check - hits the base URL.
        Can be called during agent initialization without async context.

        Returns:
            Dictionary with:
            - success: bool
            - message: str (if successful)
            - error: str (if failed)
        """
        try:
            response = httpx.get(self.base_url, timeout=5.0)
            if response.status_code == 200:
                return {"success": True, "message": "MCP server is reachable"}
            return {"success": False, "error": f"Unexpected status: {response.status_code}"}
        except httpx.ConnectError:
            return {"success": False, "error": f"Cannot connect to {self.base_url}"}
        except httpx.TimeoutException:
            return {"success": False, "error": "Connection timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to the MCP server.

        First checks basic HTTP connectivity, then tries to call test_rails_integration
        to verify the Rails environment is properly configured.

        Returns:
            Dictionary with connection test results including:
            - success: bool
            - rails_version: str (if successful)
            - database: str (if successful)
            - error: str (if failed)
        """
        try:
            # First, check basic HTTP connectivity
            async with httpx.AsyncClient(timeout=BHIVE_MCP_TIMEOUT) as client:
                # Test base URL is reachable
                health_response = await client.get(self.base_url)
                if health_response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Server returned status {health_response.status_code}"
                    }

            # Try to call the test tool
            result = await self.call_tool("test_rails_integration", {})
            print(f"[BHiveMCPClient] test_connection raw result: {result}")

            mcp_result = result.get("result", {})
            print(f"[BHiveMCPClient] test_connection mcp_result: {mcp_result}")

            # Handle MCP content array format: {"content": [{"type": "text", "text": "..."}]}
            if isinstance(mcp_result, dict) and "content" in mcp_result:
                content = mcp_result.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    first_content = content[0]
                    if isinstance(first_content, dict) and first_content.get("type") == "text":
                        text_content = first_content.get("text", "")
                        print(f"[BHiveMCPClient] Extracted text content: {text_content[:200]}...")
                        # Try to parse text as JSON
                        try:
                            mcp_result = json.loads(text_content)
                            print(f"[BHiveMCPClient] Parsed JSON from text: {list(mcp_result.keys())}")
                        except json.JSONDecodeError:
                            # Text content is not JSON, treat as success message
                            return {
                                "success": True,
                                "message": text_content
                            }

            # Check for success - handle different response formats
            if isinstance(mcp_result, dict):
                if mcp_result.get("status") == "success":
                    return {
                        "success": True,
                        "rails_version": mcp_result.get("rails_version"),
                        "database": mcp_result.get("database"),
                        "models": mcp_result.get("models", {})
                    }
                # If we got a result dict but no "status" field, check for other success indicators
                elif "rails_version" in mcp_result or "database" in mcp_result:
                    return {
                        "success": True,
                        "rails_version": mcp_result.get("rails_version"),
                        "database": mcp_result.get("database"),
                        "models": mcp_result.get("models", {})
                    }

            return {
                "success": False,
                "error": mcp_result.get("message", f"Unexpected response format: {mcp_result}")
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": f"Cannot connect to MCP server at {self.base_url}"
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": f"Connection to MCP server timed out"
            }
        except json.JSONDecodeError as e:
            # Server returned non-JSON response - might be SSE-only endpoint
            return {
                "success": False,
                "error": f"Server returned non-JSON response (MCP endpoint may require SSE transport): {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def validate_provisioning_data(self, accounts: list) -> Dict[str, Any]:
        """
        Validate provisioning data before creating resources.

        Args:
            accounts: List of account configurations to validate

        Returns:
            Validation results with errors and warnings
        """
        result = await self.call_tool("validate_provisioning_data", {
            "accounts": accounts
        })
        return self._parse_mcp_result(result)

    async def provision_complete_customer(
        self,
        customer_name: str,
        domain: str,
        time_zone: str,
        locations: list,
        sales_channel_type: str = "direct_sales",
        cancel_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Provision a complete customer with account, locations, users, and phone numbers.

        This is the main orchestration tool that creates everything in one call.

        Args:
            customer_name: Name of the customer/account
            domain: Unique SIP domain for the account
            time_zone: IANA timezone (e.g., "America/New_York")
            locations: List of location configurations, each containing:
                - name: Location name
                - address: Address object with address, city, state, zip
                - contract: Contract object with duration, payment_term, auto_activate
                - users: List of user objects
                - phone_numbers: List of phone numbers (E.164 format)
            sales_channel_type: "direct_sales" or "channel_sales"
            cancel_event: Optional asyncio.Event for cancellation support

        Returns:
            Provisioning results including created resources and any errors

        Raises:
            CancellationRequestedError: If the operation was cancelled
        """
        result = await self.call_tool(
            "provision_complete_customer",
            {
                "customer_name": customer_name,
                "domain": domain,
                "time_zone": time_zone,
                "locations": locations,
                "sales_channel_type": sales_channel_type
            },
            cancel_event=cancel_event
        )
        return self._parse_mcp_result(result)

    async def get_provisioning_status(self, job_id: str, job_type: str = "batch_import") -> Dict[str, Any]:
        """
        Check status of an asynchronous provisioning job.

        Used for bulk user imports (100+ users) which run asynchronously.

        Args:
            job_id: The Sidekiq job ID returned from create_users_bulk
            job_type: Type of job (default: "batch_import")

        Returns:
            Job status including progress percentage and completion state
        """
        result = await self.call_tool("get_provisioning_status", {
            "job_id": job_id,
            "job_type": job_type
        })
        return self._parse_mcp_result(result)
