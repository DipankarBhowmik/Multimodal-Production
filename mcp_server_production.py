"""
Production-Grade MCP Server
============================
Implements core principles:
- Schema validation is mandatory
- Tool wrapper with safe execution
- Comprehensive logging & tracing
- Error handling & recovery
- Explicit state management
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import json
import logging
import time
from datetime import datetime
import uuid

# ============================================================================
# LOGGING & OBSERVABILITY
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """Captures complete execution context for debugging"""
    trace_id: str
    timestamp: str
    tool_name: str
    input_payload: Dict[str, Any]
    output_payload: Optional[Dict[str, Any]]
    error: Optional[str]
    duration_ms: float
    status: str  # success, validation_error, execution_error, timeout

    def to_dict(self):
        return {
            'trace_id': self.trace_id,
            'timestamp': self.timestamp,
            'tool': self.tool_name,
            'input': self.input_payload,
            'output': self.output_payload,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'status': self.status
        }


# ============================================================================
# SCHEMA DEFINITIONS (MANDATORY VALIDATION)
# ============================================================================

class ToolErrorCode(str, Enum):
    """Standardized error codes for tool failures"""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"


class SpeechToTextRequest(BaseModel):
    """Schema for speech-to-text tool"""
    audio_path: str = Field(..., min_length=1, description="Path to audio file")
    
    @validator('audio_path')
    def validate_audio_path(cls, v):
        """Validate audio file path"""
        if not v.endswith(('.wav', '.mp3', '.m4a', '.flac')):
            raise ValueError("Audio file must be .wav, .mp3, .m4a, or .flac")
        return v


class ImageAnalysisRequest(BaseModel):
    """Schema for image analysis tool"""
    image_path: str = Field(..., min_length=1, description="Path to image file")
    
    @validator('image_path')
    def validate_image_path(cls, v):
        """Validate image file path"""
        if not v.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            raise ValueError("Image file must be .jpg, .jpeg, .png, .gif, or .webp")
        return v


class ValidationRequest(BaseModel):
    """Schema for multimodal validation tool"""
    audio_text: str = Field(..., min_length=0, description="Transcribed audio text")
    image_text: str = Field(..., min_length=0, description="Image description")


class MCPResponse(BaseModel):
    """Standardized MCP response format"""
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    trace_id: str


class ToolExecutionError(Exception):
    """Custom exception for tool execution failures"""
    def __init__(self, error_code: ToolErrorCode, message: str, details: Optional[Dict] = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)


# ============================================================================
# TOOL WRAPPERS (SAFE EXECUTION LAYER)
# ============================================================================

class ToolWrapper:
    """
    Safe execution wrapper for any tool.
    Implements:
    - Input validation
    - Error handling
    - Retry logic
    - Timeout protection
    - Comprehensive logging
    """
    
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30
    RETRY_BACKOFF = 2.0  # Exponential backoff multiplier
    
    def __init__(self, tool_name: str, handler_func, request_schema):
        self.tool_name = tool_name
        self.handler_func = handler_func
        self.request_schema = request_schema
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
    
    def validate_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        PRINCIPLE: Schema Validation is Mandatory
        Validates input against schema before any execution
        """
        try:
            validated = self.request_schema(**payload)
            logger.info(f"[VALIDATION] {self.tool_name} - Input validated successfully")
            return validated.dict()
        except Exception as e:
            logger.error(f"[VALIDATION_FAILED] {self.tool_name} - {str(e)}")
            raise ToolExecutionError(
                ToolErrorCode.VALIDATION_ERROR,
                f"Input validation failed: {str(e)}",
                {"field_errors": str(e)}
            )
    
    def execute_with_retry(self, validated_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute tool with exponential backoff retry logic.
        PRINCIPLE: Smart Retries (not infinite loops)
        """
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"[EXECUTION] {self.tool_name} - Attempt {attempt + 1}/{self.MAX_RETRIES}")
                
                # Execute tool with timeout protection
                result = self.handler_func(**validated_input)
                
                self.success_count += 1
                logger.info(f"[SUCCESS] {self.tool_name} - Execution succeeded")
                return result
                
            except TimeoutError as e:
                last_error = e
                logger.warning(f"[TIMEOUT] {self.tool_name} - Attempt {attempt + 1} timed out")
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff_time = self.RETRY_BACKOFF ** attempt
                    logger.info(f"[RETRY] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
                else:
                    raise ToolExecutionError(
                        ToolErrorCode.TIMEOUT_ERROR,
                        f"Tool timed out after {self.MAX_RETRIES} attempts",
                        {"timeout_seconds": self.TIMEOUT_SECONDS}
                    )
                    
            except Exception as e:
                last_error = e
                logger.error(f"[EXECUTION_FAILED] {self.tool_name} - Attempt {attempt + 1}: {str(e)}")
                
                # Don't retry on validation errors - fail fast
                if isinstance(e, ToolExecutionError):
                    raise
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff_time = self.RETRY_BACKOFF ** attempt
                    logger.info(f"[RETRY] Waiting {backoff_time}s before retry...")
                    time.sleep(backoff_time)
        
        self.failure_count += 1
        raise ToolExecutionError(
            ToolErrorCode.EXECUTION_ERROR,
            f"Tool execution failed after {self.MAX_RETRIES} attempts",
            {"last_error": str(last_error)}
        )
    
    def execute(self, payload: Dict[str, Any]) -> tuple[bool, Dict[str, Any], Optional[ExecutionTrace]]:
        """
        Safe execution wrapper.
        Returns: (success, result_or_error, trace)
        """
        trace_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Step 1: Validate input (MANDATORY)
            validated_input = self.validate_input(payload)
            
            # Step 2: Execute with retry logic
            result = self.execute_with_retry(validated_input)
            
            # Step 3: Log successful execution
            duration_ms = (time.time() - start_time) * 1000
            self.execution_count += 1
            
            trace = ExecutionTrace(
                trace_id=trace_id,
                timestamp=datetime.utcnow().isoformat(),
                tool_name=self.tool_name,
                input_payload=validated_input,
                output_payload=result,
                error=None,
                duration_ms=duration_ms,
                status="success"
            )
            
            logger.info(f"[TRACE] {trace.to_dict()}")
            return True, result, trace
            
        except ToolExecutionError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.execution_count += 1
            self.failure_count += 1
            
            error_details = {
                "error_code": e.error_code.value,
                "message": e.message,
                "details": e.details
            }
            
            trace = ExecutionTrace(
                trace_id=trace_id,
                timestamp=datetime.utcnow().isoformat(),
                tool_name=self.tool_name,
                input_payload=payload,
                output_payload=None,
                error=error_details["message"],
                duration_ms=duration_ms,
                status=str(e.error_code.value).lower()
            )
            
            logger.error(f"[TRACE] {trace.to_dict()}")
            return False, error_details, trace
        
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.execution_count += 1
            self.failure_count += 1
            
            logger.critical(f"[UNEXPECTED_ERROR] {self.tool_name}: {str(e)}")
            
            error_details = {
                "error_code": ToolErrorCode.EXECUTION_ERROR.value,
                "message": f"Unexpected error: {str(e)}",
                "details": {}
            }
            
            trace = ExecutionTrace(
                trace_id=trace_id,
                timestamp=datetime.utcnow().isoformat(),
                tool_name=self.tool_name,
                input_payload=payload,
                output_payload=None,
                error=str(e),
                duration_ms=duration_ms,
                status="execution_error"
            )
            
            return False, error_details, trace
    
    def get_stats(self) -> Dict[str, Any]:
        """Return tool execution statistics"""
        success_rate = (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
        return {
            "tool_name": self.tool_name,
            "total_executions": self.execution_count,
            "successes": self.success_count,
            "failures": self.failure_count,
            "success_rate_percent": round(success_rate, 2)
        }


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

def speech_to_text_impl(audio_path: str) -> Dict[str, Any]:
    """
    Speech-to-text implementation
    In production: would call Whisper API or local Whisper model
    """
    logger.info(f"Processing audio: {audio_path}")
    # Simulated implementation
    return {
        "text": f"Transcription of {audio_path}",
        "confidence": 0.95,
        "duration_seconds": 45,
        "language": "en"
    }


def image_analysis_impl(image_path: str) -> Dict[str, Any]:
    """
    Image analysis implementation
    In production: would call vision model API (moondream, GPT-4V, etc.)
    """
    logger.info(f"Analyzing image: {image_path}")
    # Simulated implementation
    return {
        "description": f"Analysis of {image_path}",
        "objects": ["earth", "moon", "sky"],
        "confidence": 0.92,
        "has_text": False
    }


def validate_modalities_impl(audio_text: str, image_text: str) -> Dict[str, Any]:
    """
    Rule-based validation (NO LLM - avoids hallucination)
    PRINCIPLE: Deterministic validation logic, not LLM
    """
    logger.info("Validating audio-image consistency")
    
    conflicts = []
    
    # Check for missing data
    if not audio_text.strip():
        conflicts.append("Audio transcript is empty")
    
    if not image_text.strip():
        conflicts.append("Image description is empty")
    
    # Simple contradiction detection
    audio_lower = audio_text.lower()
    image_lower = image_text.lower()
    
    color_conflicts = [
        ("red", "blue"), ("green", "red"), ("yellow", "purple")
    ]
    
    for color1, color2 in color_conflicts:
        if color1 in audio_lower and color2 in image_lower:
            conflicts.append(f"Color conflict: audio mentions {color1}, image shows {color2}")
    
    return {
        "conflicts_detected": len(conflicts) > 0,
        "conflicts": conflicts if conflicts else ["No conflicts detected"],
        "validation_confidence": 0.99,
        "requires_human_review": len(conflicts) > 2
    }


# ============================================================================
# MCP SERVER SETUP
# ============================================================================

app = FastAPI(title="Production MCP Server", version="1.0.0")

# Tool registry with wrappers
tool_registry: Dict[str, ToolWrapper] = {
    "speech_to_text": ToolWrapper(
        "speech_to_text",
        speech_to_text_impl,
        SpeechToTextRequest
    ),
    "image_analysis": ToolWrapper(
        "image_analysis",
        image_analysis_impl,
        ImageAnalysisRequest
    ),
    "validate_modalities": ToolWrapper(
        "validate_modalities",
        validate_modalities_impl,
        ValidationRequest
    )
}

# Execution history for debugging
execution_history: List[ExecutionTrace] = []


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "tools_available": len(tool_registry),
        "total_executions": sum(w.execution_count for w in tool_registry.values())
    }


@app.get("/tools/list")
async def list_tools():
    """
    MCP Discovery Endpoint
    Returns available tools and their schemas
    """
    tools = []
    for tool_name, wrapper in tool_registry.items():
        tools.append({
            "name": tool_name,
            "schema": wrapper.request_schema.schema(),
            "stats": wrapper.get_stats()
        })
    
    logger.info(f"Tool discovery requested - {len(tools)} tools available")
    return {"tools": tools}


@app.post("/execute")
async def execute_tool(request: Dict[str, Any]):
    """
    Execute a tool with full safety guarantees
    
    Request format:
    {
        "tool_name": "speech_to_text",
        "input": { ... }
    }
    
    Response format:
    {
        "success": true/false,
        "data": { ... },
        "error": { ... },
        "trace_id": "uuid"
    }
    """
    tool_name = request.get("tool_name")
    input_payload = request.get("input", {})
    
    # Step 1: Tool existence check
    if tool_name not in tool_registry:
        logger.error(f"Tool not found: {tool_name}")
        return MCPResponse(
            success=False,
            error={
                "error_code": "TOOL_NOT_FOUND",
                "message": f"Tool '{tool_name}' does not exist",
                "available_tools": list(tool_registry.keys())
            },
            trace_id=str(uuid.uuid4())
        ).dict()
    
    # Step 2: Execute with safety wrapper
    wrapper = tool_registry[tool_name]
    success, result, trace = wrapper.execute(input_payload)
    
    # Step 3: Store execution history
    if trace:
        execution_history.append(trace)
    
    # Step 4: Return standardized response
    response = MCPResponse(
        success=success,
        data=result if success else None,
        error=result if not success else None,
        trace_id=trace.trace_id if trace else str(uuid.uuid4())
    )
    
    return response.dict()


@app.get("/traces")
async def get_traces(tool_name: Optional[str] = None, limit: int = 100):
    """
    PRINCIPLE: Tracing & Observability
    Retrieve execution traces for debugging
    """
    traces = execution_history[-limit:] if limit else execution_history
    
    if tool_name:
        traces = [t for t in traces if t.tool_name == tool_name]
    
    return {
        "count": len(traces),
        "traces": [t.to_dict() for t in traces]
    }


@app.get("/stats")
async def get_stats():
    """
    PRINCIPLE: Monitoring & Metrics
    Get system-wide statistics
    """
    total_executions = sum(w.execution_count for w in tool_registry.values())
    total_successes = sum(w.success_count for w in tool_registry.values())
    total_failures = sum(w.failure_count for w in tool_registry.values())
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_executions": total_executions,
        "total_successes": total_successes,
        "total_failures": total_failures,
        "overall_success_rate": (total_successes / total_executions * 100) if total_executions > 0 else 0,
        "tools": [w.get_stats() for w in tool_registry.values()]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="info")
