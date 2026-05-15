"""
Production-Grade MCP Client
============================
Implements:
- Dynamic tool discovery
- Local schema caching
- Preflight validation
- Safe tool invocation
- Comprehensive error handling
"""

import requests
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


@dataclass
class ToolSchema:
    """Represents a tool's schema"""
    name: str
    schema: Dict[str, Any]
    
    def validate_input(self, payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Preflight input validation before execution
        PRINCIPLE: Validate before execution
        """
        required_fields = self.schema.get('required', [])
        
        # Check required fields
        for field in required_fields:
            if field not in payload:
                return False, f"Missing required field: {field}"
        
        # Check field types (basic validation)
        properties = self.schema.get('properties', {})
        for field, value in payload.items():
            if field in properties:
                field_schema = properties[field]
                expected_type = field_schema.get('type')
                
                # Type validation
                if expected_type and not self._check_type(value, expected_type):
                    return False, f"Field '{field}' has wrong type. Expected {expected_type}"
        
        return True, None
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            'string': str,
            'number': (int, float),
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict
        }
        
        expected_python_type = type_map.get(expected_type)
        if expected_python_type:
            return isinstance(value, expected_python_type)
        return True


class MCPClient:
    """
    Safe MCP Client
    - Discovers tools once at startup
    - Caches schemas locally
    - Validates inputs before sending
    - Handles errors gracefully
    - Retries with backoff
    """
    
    def __init__(self, server_url: str = "http://127.0.0.1:9000"):
        self.server_url = server_url
        self.connected = False
        self.tool_cache: Dict[str, ToolSchema] = {}
        self.session = requests.Session()
        self.session.timeout = 30
        
        # Retry configuration
        self.max_retries = 3
        self.retry_backoff = 2.0
        
        logger.info(f"MCPClient initialized - Server: {server_url}")
    
    def health_check(self) -> bool:
        """Check server health before operations"""
        try:
            response = self.session.get(f"{self.server_url}/health")
            response.raise_for_status()
            logger.info("Server health check passed")
            return True
        except Exception as e:
            logger.error(f"Server health check failed: {str(e)}")
            return False
    
    def connect(self) -> bool:
        """
        Connection Phase
        - Check server health
        - Discover available tools
        - Cache schemas locally
        """
        if not self.health_check():
            return False
        
        try:
            logger.info("Starting tool discovery...")
            response = self.session.get(f"{self.server_url}/tools/list")
            response.raise_for_status()
            
            data = response.json()
            tools = data.get('tools', [])
            
            # Cache all tool schemas
            for tool_info in tools:
                tool_name = tool_info['name']
                tool_schema = tool_info['schema']
                
                self.tool_cache[tool_name] = ToolSchema(
                    name=tool_name,
                    schema=tool_schema
                )
                
                logger.info(f"Cached schema for tool: {tool_name}")
            
            self.connected = True
            logger.info(f"Connected! Discovered {len(self.tool_cache)} tools")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return False
    
    def available_tools(self) -> List[str]:
        """
        Get list of available tools
        PRINCIPLE: Tools are discovered once, cached locally
        """
        if not self.connected:
            raise RuntimeError("Client not connected. Call connect() first.")
        
        tools = list(self.tool_cache.keys())
        logger.info(f"Available tools: {tools}")
        return tools
    
    def get_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get schema for a specific tool"""
        if tool_name in self.tool_cache:
            return self.tool_cache[tool_name].schema
        return None
    
    def _preflight_validate(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Preflight validation - check inputs BEFORE sending to server
        PRINCIPLE: Fail fast locally before remote execution
        """
        if tool_name not in self.tool_cache:
            return False, f"Tool '{tool_name}' not found in cache"
        
        schema = self.tool_cache[tool_name]
        is_valid, error = schema.validate_input(arguments)
        
        if not is_valid:
            logger.warning(f"Preflight validation failed for {tool_name}: {error}")
        
        return is_valid, error
    
    def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """
        Invoke a tool safely
        
        Flow:
        1. Check connection
        2. Tool existence check
        3. Preflight validation
        4. Execute with retry
        5. Return result
        """
        
        if not self.connected:
            return False, {
                "error_code": "NOT_CONNECTED",
                "message": "Client not connected. Call connect() first."
            }
        
        # Step 1: Tool existence check
        if tool_name not in self.tool_cache:
            logger.error(f"Tool not found in cache: {tool_name}")
            return False, {
                "error_code": "TOOL_NOT_FOUND",
                "message": f"Tool '{tool_name}' not available",
                "available_tools": self.available_tools()
            }
        
        # Step 2: Preflight validation (FAIL FAST)
        is_valid, error_msg = self._preflight_validate(tool_name, arguments)
        if not is_valid:
            logger.error(f"Preflight validation failed: {error_msg}")
            return False, {
                "error_code": "VALIDATION_ERROR",
                "message": error_msg
            }
        
        # Step 3: Execute with retry logic
        return self._invoke_with_retry(tool_name, arguments)
    
    def _invoke_with_retry(self, tool_name: str, arguments: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """
        Execute tool with exponential backoff retry
        PRINCIPLE: Smart retries with exponential backoff
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Invoking {tool_name} - Attempt {attempt + 1}/{self.max_retries}")
                
                payload = {
                    "tool_name": tool_name,
                    "input": arguments
                }
                
                response = self.session.post(
                    f"{self.server_url}/execute",
                    json=payload,
                    timeout=30
                )
                
                # Check HTTP status
                if response.status_code >= 500:
                    # Server error - retry
                    last_error = f"Server error: {response.status_code}"
                    if attempt < self.max_retries - 1:
                        backoff = self.retry_backoff ** attempt
                        logger.warning(f"Server error, retrying in {backoff}s...")
                        import time
                        time.sleep(backoff)
                        continue
                else:
                    response.raise_for_status()
                
                # Parse response
                data = response.json()
                
                if data.get('success'):
                    logger.info(f"Successfully invoked {tool_name}")
                    return True, data.get('data', {})
                else:
                    # Tool execution failed
                    logger.error(f"{tool_name} execution failed: {data.get('error')}")
                    return False, data.get('error', {})
                
            except requests.Timeout:
                last_error = "Request timeout"
                logger.warning(f"Timeout on {tool_name}, attempt {attempt + 1}")
                
                if attempt < self.max_retries - 1:
                    backoff = self.retry_backoff ** attempt
                    logger.info(f"Retrying in {backoff}s...")
                    import time
                    time.sleep(backoff)
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error invoking {tool_name}: {str(e)}")
                
                if attempt < self.max_retries - 1:
                    backoff = self.retry_backoff ** attempt
                    logger.info(f"Retrying in {backoff}s...")
                    import time
                    time.sleep(backoff)
        
        # All retries exhausted
        logger.error(f"Failed to invoke {tool_name} after {self.max_retries} attempts")
        return False, {
            "error_code": "EXECUTION_FAILED",
            "message": f"Tool invocation failed after {self.max_retries} attempts",
            "last_error": last_error
        }
    
    def get_server_stats(self) -> Optional[Dict[str, Any]]:
        """Get server statistics"""
        try:
            response = self.session.get(f"{self.server_url}/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get server stats: {str(e)}")
            return None
    
    def get_traces(self, tool_name: Optional[str] = None, limit: int = 50) -> Optional[List[Dict]]:
        """
        PRINCIPLE: Tracing for observability
        Retrieve execution traces for debugging
        """
        try:
            params = {'limit': limit}
            if tool_name:
                params['tool_name'] = tool_name
            
            response = self.session.get(f"{self.server_url}/traces", params=params)
            response.raise_for_status()
            
            data = response.json()
            return data.get('traces', [])
            
        except Exception as e:
            logger.error(f"Failed to get traces: {str(e)}")
            return None


def create_client(server_url: str = "http://127.0.0.1:9000") -> MCPClient:
    """Factory function to create and connect client"""
    client = MCPClient(server_url)
    if client.connect():
        return client
    else:
        raise RuntimeError("Failed to connect to MCP server")
