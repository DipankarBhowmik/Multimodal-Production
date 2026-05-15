"""
Production-Grade Agent System
==============================
Implements:
- PRINCIPLE: Agents = Execution Loops (not one-time calls)
- PRINCIPLE: Explicit state management
- PRINCIPLE: Clear control flow with logging
- Tool chaining with state passing
- Comprehensive error handling
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import uuid

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class StepStatus(str, Enum):
    """Individual step status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of a single step execution"""
    step_id: str
    tool_name: str
    status: StepStatus
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    error: Optional[str]
    duration_ms: float
    timestamp: str
    
    def to_dict(self):
        return {
            'step_id': self.step_id,
            'tool': self.tool_name,
            'status': self.status.value,
            'input': self.input_data,
            'output': self.output_data,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'timestamp': self.timestamp
        }


@dataclass
class AgentState:
    """
    PRINCIPLE: Explicit State Management
    Complete state snapshot of agent execution
    """
    agent_id: str
    user_input: str
    current_step: int = 0
    status: AgentStatus = AgentStatus.IDLE
    context: Dict[str, Any] = field(default_factory=dict)  # Shared memory across steps
    execution_history: List[StepResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def add_step_result(self, result: StepResult):
        """Add step result to history"""
        self.execution_history.append(result)
        logger.info(f"Step {result.step_id} completed with status: {result.status.value}")
    
    def add_error(self, error: str):
        """Add error to error list"""
        self.errors.append(error)
        logger.error(f"Agent error: {error}")
    
    def get_context_value(self, key: str, default: Any = None) -> Any:
        """Get value from context"""
        return self.context.get(key, default)
    
    def set_context_value(self, key: str, value: Any):
        """Set value in context"""
        self.context[key] = value
        logger.info(f"Context updated: {key} = {json.dumps(str(value)[:100])}")
    
    def to_dict(self):
        """Serialize state to dict"""
        return {
            'agent_id': self.agent_id,
            'user_input': self.user_input,
            'current_step': self.current_step,
            'status': self.status.value,
            'context': self.context,
            'execution_history': [r.to_dict() for r in self.execution_history],
            'errors': self.errors,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }


@dataclass
class ToolDefinition:
    """Definition of a tool that can be called by agent"""
    tool_name: str
    handler: Callable
    description: str
    required_context_keys: List[str] = field(default_factory=list)


class ExecutionLoop:
    """
    PRINCIPLE: Agents are Execution Loops
    Not a single call, but a continuous loop:
    - Observe current state
    - Decide next action
    - Act using tools
    - Update state
    - Repeat or stop
    """
    
    def __init__(self, agent_id: Optional[str] = None):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.tools: Dict[str, ToolDefinition] = {}
        self.state: Optional[AgentState] = None
        logger.info(f"ExecutionLoop created: {self.agent_id}")
    
    def register_tool(self, tool_def: ToolDefinition):
        """Register a tool for use in the loop"""
        self.tools[tool_def.tool_name] = tool_def
        logger.info(f"Tool registered: {tool_def.tool_name}")
    
    def initialize(self, user_input: str):
        """
        Initialize agent state
        PRINCIPLE: Explicit state at every step
        """
        self.state = AgentState(
            agent_id=self.agent_id,
            user_input=user_input,
            started_at=datetime.utcnow().isoformat()
        )
        logger.info(f"Agent initialized with input: {user_input[:100]}")
    
    def _prepare_tool_input(self, tool_input_template: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """
        Prepare tool input by resolving context placeholders
        Example: {"amount": "{{budget}}"} -> {"amount": 1000}
        """
        resolved_input = {}
        
        for key, value in tool_input_template.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                # This is a context reference
                context_key = value[2:-2].strip()
                resolved_value = self.state.get_context_value(context_key)
                
                if resolved_value is None:
                    return False, {
                        "error": f"Missing context key: {context_key}",
                        "available_keys": list(self.state.context.keys())
                    }
                
                resolved_input[key] = resolved_value
                logger.info(f"Resolved {{{{ {context_key} }}}} -> {resolved_value}")
            else:
                resolved_input[key] = value
        
        return True, resolved_input
    
    def execute_step(self, step_id: str, tool_name: str, tool_input: Dict[str, Any]) -> StepResult:
        """
        Execute a single step
        
        Returns: StepResult with complete trace information
        """
        import time
        start_time = time.time()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP: {step_id} | TOOL: {tool_name}")
        logger.info(f"{'='*60}")
        
        # Validate tool exists
        if tool_name not in self.tools:
            error_msg = f"Tool '{tool_name}' not found"
            logger.error(error_msg)
            
            return StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=StepStatus.FAILED,
                input_data=tool_input,
                output_data=None,
                error=error_msg,
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow().isoformat()
            )
        
        # Prepare input (resolve context variables)
        success, prepared_input = self._prepare_tool_input(tool_input)
        if not success:
            error_msg = prepared_input.get("error", "Unknown error")
            logger.error(f"Input preparation failed: {error_msg}")
            
            return StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=StepStatus.FAILED,
                input_data=tool_input,
                output_data=None,
                error=error_msg,
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow().isoformat()
            )
        
        logger.info(f"Input prepared: {json.dumps(prepared_input, indent=2)}")
        
        # Execute tool
        try:
            tool_def = self.tools[tool_name]
            logger.info(f"Calling tool handler...")
            
            # Call the tool handler
            result = tool_def.handler(**prepared_input)
            
            logger.info(f"Tool execution succeeded: {json.dumps(str(result)[:200])}")
            
            # Create step result
            step_result = StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=StepStatus.SUCCESS,
                input_data=prepared_input,
                output_data=result,
                error=None,
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow().isoformat()
            )
            
            return step_result
            
        except Exception as e:
            error_msg = f"Tool execution error: {str(e)}"
            logger.error(error_msg)
            
            return StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=StepStatus.FAILED,
                input_data=prepared_input,
                output_data=None,
                error=error_msg,
                duration_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow().isoformat()
            )
    
    def run_pipeline(self, steps: List[Dict[str, Any]]) -> AgentState:
        """
        PRINCIPLE: Agents = Execution Loop
        Run a sequence of steps with explicit state management
        
        Step format:
        {
            "step_id": "extract_intent",
            "tool": "parse_input",
            "input": {...},
            "context_output_key": "intent"  # Store result in state.context
        }
        """
        if not self.state:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        self.state.status = AgentStatus.RUNNING
        logger.info(f"\nStarting pipeline with {len(steps)} steps\n")
        
        for i, step_def in enumerate(steps):
            self.state.current_step = i + 1
            
            step_id = step_def.get('step_id', f'step_{i}')
            tool_name = step_def.get('tool')
            tool_input = step_def.get('input', {})
            context_key = step_def.get('context_output_key', step_id)
            
            # Execute step
            step_result = self.execute_step(step_id, tool_name, tool_input)
            
            # Add to history
            self.state.add_step_result(step_result)
            
            # PRINCIPLE: Failure handling
            if step_result.status == StepStatus.FAILED:
                error_msg = step_result.error or "Unknown error"
                self.state.add_error(error_msg)
                self.state.status = AgentStatus.FAILED
                
                logger.error(f"\n❌ PIPELINE STOPPED - Step '{step_id}' failed")
                logger.error(f"Error: {error_msg}")
                
                # IMPORTANT: Stop on failure
                # Do NOT continue with corrupted state
                break
            
            # Update context with step output
            if step_result.output_data:
                self.state.set_context_value(context_key, step_result.output_data)
            
            logger.info(f"✅ Step completed: {step_id}\n")
        
        # Mark completion
        if self.state.status != AgentStatus.FAILED:
            self.state.status = AgentStatus.COMPLETED
        
        self.state.completed_at = datetime.utcnow().isoformat()
        
        logger.info(f"\n{'='*60}")
        logger.info(f"AGENT EXECUTION COMPLETE")
        logger.info(f"Status: {self.state.status.value}")
        logger.info(f"Steps executed: {len(self.state.execution_history)}")
        logger.info(f"Errors: {len(self.state.errors)}")
        logger.info(f"{'='*60}\n")
        
        return self.state
    
    def get_final_result(self) -> Optional[Dict[str, Any]]:
        """
        Get final agent result from context
        Usually stored by the last step
        """
        if not self.state:
            return None
        
        if self.state.status != AgentStatus.COMPLETED:
            return {
                "error": f"Agent not completed. Status: {self.state.status.value}",
                "errors": self.state.errors
            }
        
        # Return final output from context
        final_output = self.state.get_context_value('final_output')
        if final_output:
            return final_output
        
        # Or return entire context if no specific final output
        return {"context": self.state.context}
    
    def get_execution_trace(self) -> Dict[str, Any]:
        """
        PRINCIPLE: Tracing for observability
        Get complete execution trace for debugging
        """
        if not self.state:
            return {}
        
        return self.state.to_dict()


# ============================================================================
# AGENT FACTORY
# ============================================================================

def create_multimodal_agent_pipeline(client) -> List[Dict[str, Any]]:
    """
    Factory function to create the multimodal agent pipeline
    
    Pipeline:
    1. Extract intent from user input
    2. Process audio -> speech_to_text
    3. Process image -> image_analysis
    4. Validate consistency
    5. Generate final response
    """
    
    return [
        {
            "step_id": "setup_execution",
            "tool": "setup",
            "input": {},
            "context_output_key": "execution_id"
        },
        {
            "step_id": "speech_to_text",
            "tool": "speech_to_text",
            "input": {"audio_path": "inputs/moon.wav"},
            "context_output_key": "audio_transcript"
        },
        {
            "step_id": "image_analysis",
            "tool": "image_analysis",
            "input": {"image_path": "inputs/earth.jpg"},
            "context_output_key": "image_description"
        },
        {
            "step_id": "validate_consistency",
            "tool": "validate_modalities",
            "input": {
                "audio_text": "{{audio_transcript}}",
                "image_text": "{{image_description}}"
            },
            "context_output_key": "validation_report"
        },
        {
            "step_id": "generate_response",
            "tool": "synthesize_response",
            "input": {
                "transcript": "{{audio_transcript}}",
                "description": "{{image_description}}",
                "validation": "{{validation_report}}"
            },
            "context_output_key": "final_output"
        }
    ]
