# Production Multimodal AI Agent System - Setup & Deployment Guide

## Table of Contents
1. [System Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the System](#running)
7. [Monitoring & Debugging](#monitoring)
8. [Deployment](#deployment)
9. [Production Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## System Overview

This is a production-grade multimodal AI agent system that implements enterprise-scale principles:

**Key Principles:**
- ✅ Schema validation is mandatory
- ✅ Safe tool execution with retries
- ✅ Explicit agent execution loops (not one-shot calls)
- ✅ Structured state management
- ✅ Comprehensive observability & tracing
- ✅ Multi-agent coordination via CrewAI
- ✅ MCP (Model Context Protocol) for tool standardization

**Components:**
- MCP Server (FastAPI) - Exposes tools with validation
- MCP Client - Discovers tools, validates inputs, invokes safely
- Agent Execution Loop - Explicit pipeline with state
- CrewAI Multi-Agent System - Specialized agents with roles
- Monitoring & Observability - Traces, metrics, performance data

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER REQUEST                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              MAIN ORCHESTRATION SCRIPT                       │
│         (Coordinates phases and execution flow)              │
└─────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────┴──────────────────┐
        ↓                                     ↓
┌─────────────────────────┐      ┌───────────────────────┐
│  EXECUTION LOOP PHASE   │      │  CREWAI MULTI-AGENT   │
│  (Explicit Pipeline)    │      │  (Role-Based Agents)  │
│                         │      │                       │
│ 1. Setup                │      │ Audio Agent           │
│ 2. Speech-to-Text       │      │ Vision Agent          │
│ 3. Image Analysis       │      │ Validation Agent      │
│ 4. Validate             │      │ Reasoning Agent       │
│ 5. Synthesize           │      │                       │
└─────────────────────────┘      └───────────────────────┘
        ↓                                     ↓
        └──────────────────┬──────────────────┘
                           ↓
        ┌──────────────────────────────────────┐
        │    TOOL EXECUTION LAYER (MCP)        │
        │                                      │
        │ ┌──────────────────────────────────┐ │
        │ │  MCP Client (Safe Invocation)    │ │
        │ │ - Discovery                      │ │
        │ │ - Validation                     │ │
        │ │ - Retry with backoff             │ │
        │ └──────────────────────────────────┘ │
        │                ↓                     │
        │ ┌──────────────────────────────────┐ │
        │ │  MCP Server (FastAPI)            │ │
        │ │ - Tool Registry                  │ │
        │ │ - Schema Enforcement             │ │
        │ │ - Error Handling                 │ │
        │ │ - Tracing & Observability        │ │
        │ └──────────────────────────────────┘ │
        │                ↓                     │
        │ ┌──────────────────────────────────┐ │
        │ │  Tool Implementations            │ │
        │ │ - Speech-to-Text (Whisper)       │ │
        │ │ - Image Analysis (Vision Model)  │ │
        │ │ - Validation (Rule-Based)        │ │
        │ └──────────────────────────────────┘ │
        └──────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────┐
        │      OBSERVABILITY LAYER             │
        │ - Execution Traces                   │
        │ - Metrics & Performance              │
        │ - Error Tracking                     │
        │ - LangSmith Integration              │
        └──────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────┐
        │       RESULTS & OUTPUTS              │
        │ - JSON Results                       │
        │ - Markdown Report                    │
        │ - Execution Logs                     │
        └──────────────────────────────────────┘
```

---

## Prerequisites

### System Requirements
- **OS:** Linux, macOS, or Windows (with WSL2)
- **Python:** 3.10 or 3.11
- **RAM:** Minimum 8GB (16GB recommended)
- **Disk:** 20GB free space (for models)
- **CPU:** Multi-core processor

### Required Software
1. **Python 3.10+**
   ```bash
   python --version  # Check version
   ```

2. **FFmpeg** (for audio processing)
   - Linux: `sudo apt-get install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Windows: Download from https://www.gyan.dev/ffmpeg/builds/

3. **Ollama** (optional, for local LLM)
   - Download: https://ollama.com/download
   - Pull model: `ollama pull phi3`

4. **Git** (for version control)
   ```bash
   git --version
   ```

### API Keys
- OpenAI API key (if using GPT-4): https://platform.openai.com/api-keys
- Anthropic API key (if using Claude): https://console.anthropic.com/
- LangSmith key (for observability): https://smith.langchain.com/

---

## Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd multimodal-agent-system
```

### 2. Create Virtual Environment
```bash
# Using conda (recommended)
conda create -n multimodal_ai python=3.10
conda activate multimodal_ai

# OR using venv
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup Environment Variables
```bash
# Copy example config
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required environment variables:**
```env
# LLM Configuration
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# MCP Server
MCP_SERVER_URL=http://127.0.0.1:9000
MCP_HOST=127.0.0.1
MCP_PORT=9000

# Local LLM (Ollama)
OLLAMA_MODEL=phi3
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Observability
LANGSMITH_API_KEY=your_key_here
LANGSMITH_PROJECT_NAME=multimodal-agents

# Logging
LOG_LEVEL=INFO
LOG_FILE=agent_execution.log
```

### 5. Create Input Directory
```bash
mkdir -p inputs

# Add test files
# - inputs/earth.jpg (sample image)
# - inputs/moon.wav (sample audio)
```

---

## Configuration

### application_config.yaml
```yaml
# System Configuration
system:
  name: "Multimodal AI Agent System"
  version: "1.0.0"
  log_level: "INFO"
  
# MCP Server
mcp:
  server_url: "http://127.0.0.1:9000"
  host: "127.0.0.1"
  port: 9000
  reload: true
  
# Agent Configuration
agents:
  execution_timeout_seconds: 300
  max_retries: 3
  retry_backoff: 2.0
  
# Tools
tools:
  speech_to_text:
    model: "base"  # whisper model size
    language: "en"
  image_analysis:
    model: "moondream"
    confidence_threshold: 0.8
  
# Monitoring
monitoring:
  enable_traces: true
  enable_metrics: true
  langsmith_enabled: false
  
# Output
output:
  format: "json"  # json or markdown
  save_results: true
  results_file: "execution_results.json"
```

---

## Running the System

### Step 1: Start MCP Server
```bash
# Terminal 1
python 01_mcp_server_production.py

# Expected output:
# INFO: Uvicorn running on http://127.0.0.1:9000
```

### Step 2: Run Tests (Optional)
```bash
# Terminal 2
python 06_testing_validation_suite.py

# Should show all tests passing
```

### Step 3: Execute Main Pipeline
```bash
# Terminal 2 (or another terminal)
python 05_main_orchestration.py \
  --image inputs/earth.jpg \
  --audio inputs/moon.wav \
  --format json

# Optional arguments:
# --mcp-url http://127.0.0.1:9000  # MCP server URL
# --log-level DEBUG                 # Logging level
# --skip-loop                       # Skip execution loop
# --skip-crewai                     # Skip CrewAI phase
```

### Expected Output
```
╔══════════════════════════════════════════════════════════════════╗
║          PRODUCTION MULTIMODAL AI AGENT SYSTEM                   ║
╚══════════════════════════════════════════════════════════════════╝

PHASE 1: INITIALIZATION
- Verifying input files...
- ✓ Image verified
- ✓ Audio verified
- Connecting to MCP server...
- ✓ MCP Client connected
- Available tools: speech_to_text, image_analysis, validate_modalities

PHASE 2: EXECUTION LOOP PIPELINE
- Registering tools...
- Running pipeline...
  ✓ Step 1: setup
  ✓ Step 2: process_audio
  ✓ Step 3: process_image
  ✓ Step 4: validate
  ✓ Step 5: synthesize

PHASE 3: CREWAI MULTI-AGENT SYSTEM
- Initializing multi-agent system...
- Executing agents...
  ✓ Audio Agent
  ✓ Vision Agent
  ✓ Validation Agent
  ✓ Reasoning Agent

PHASE 4: RESULTS AGGREGATION
- Execution Summary:
  Total Duration: 45.32 seconds
  Status: COMPLETE
  Results saved to: execution_results.json
```

---

## Monitoring & Debugging

### 1. View Execution Traces
```bash
# Get recent traces
curl http://127.0.0.1:9000/traces?limit=50

# Get traces for specific tool
curl http://127.0.0.1:9000/traces?tool_name=speech_to_text&limit=10
```

### 2. Check Server Statistics
```bash
curl http://127.0.0.1:9000/stats | jq .
```

### 3. Enable Debug Logging
```bash
python 05_main_orchestration.py \
  --log-level DEBUG

# Logs will be written to agent_execution.log
tail -f agent_execution.log
```

### 4. Review Execution Results
```bash
# JSON format
cat execution_results.json | jq .

# Markdown report
cat execution_results.md | less
```

### 5. LangSmith Monitoring (Optional)
```bash
# Set in .env
LANGSMITH_API_KEY=your_key_here

# Visit dashboard at https://smith.langchain.com/
```

---

## Deployment

### Docker Deployment

#### 1. Build Docker Image
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt && \
    apt-get update && apt-get install -y ffmpeg

COPY . .

EXPOSE 9000

CMD ["python", "01_mcp_server_production.py"]
```

#### 2. Build & Run
```bash
# Build
docker build -t multimodal-ai-agent .

# Run MCP Server
docker run -p 9000:9000 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  multimodal-ai-agent

# Run Pipeline
docker run -v $(pwd)/inputs:/app/inputs \
  -v $(pwd)/outputs:/app/outputs \
  multimodal-ai-agent \
  python 05_main_orchestration.py
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: multimodal-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: multimodal-agent
  template:
    metadata:
      labels:
        app: multimodal-agent
    spec:
      containers:
      - name: mcp-server
        image: multimodal-ai-agent:latest
        ports:
        - containerPort: 9000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai
      - name: agent-pipeline
        image: multimodal-ai-agent:latest
        command: ["python", "05_main_orchestration.py"]
```

---

## Production Best Practices

### 1. Error Handling
- ✅ Always use try-catch blocks
- ✅ Log all errors with context
- ✅ Implement retry logic with backoff
- ✅ Define fallback behaviors

### 2. Observability
- ✅ Enable comprehensive logging
- ✅ Track execution traces
- ✅ Monitor performance metrics
- ✅ Set up alerts

### 3. Security
- ✅ Use environment variables for secrets
- ✅ Never commit API keys
- ✅ Validate all inputs
- ✅ Use HTTPS in production

### 4. Performance
- ✅ Cache tool schemas locally
- ✅ Implement request timeouts
- ✅ Use connection pooling
- ✅ Profile bottlenecks

### 5. Testing
- ✅ Unit test all components
- ✅ Integration test pipelines
- ✅ Load test under stress
- ✅ Automated regression tests

### 6. Maintenance
- ✅ Keep dependencies updated
- ✅ Monitor for deprecations
- ✅ Document changes
- ✅ Version control everything

---

## Troubleshooting

### Issue: MCP Server Connection Failed

**Symptom:**
```
Error: Failed to connect to MCP server at http://127.0.0.1:9000
```

**Solution:**
1. Check if server is running: `curl http://127.0.0.1:9000/health`
2. Verify port is not in use: `lsof -i :9000`
3. Check firewall settings
4. Ensure correct URL in configuration

### Issue: Audio File Not Processed

**Symptom:**
```
ERROR: audio processing failed - unsupported file format
```

**Solution:**
1. Verify file format is supported (.wav, .mp3, .m4a, .flac)
2. Check FFmpeg is installed: `ffmpeg -version`
3. Ensure file path is correct and readable

### Issue: Out of Memory

**Symptom:**
```
MemoryError: Unable to allocate memory
```

**Solution:**
1. Increase system RAM or use smaller models
2. Use model quantization
3. Process files in batches
4. Monitor memory usage: `free -h`

### Issue: Slow Execution

**Symptom:**
```
Pipeline execution taking >5 minutes
```

**Solution:**
1. Profile bottlenecks: `python -m cProfile 05_main_orchestration.py`
2. Use smaller models
3. Enable GPU acceleration
4. Parallelize where possible
5. Check network latency

### Issue: Invalid Schema Error

**Symptom:**
```
VALIDATION_ERROR: Input validation failed - Missing required field: audio_path
```

**Solution:**
1. Check input data structure
2. Verify required fields are present
3. Review schema definitions
4. Update test data

---

## Getting Help

### Documentation
- Architecture docs: `docs/ARCHITECTURE.md`
- API reference: `docs/API_REFERENCE.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`

### Support Channels
- Issues: https://github.com/your-repo/issues
- Discussions: https://github.com/your-repo/discussions
- Email: support@example.com

### Community
- Forum: https://community.example.com
- Slack: https://workspace.slack.com/invite/...
- Twitter: @example

---

## License

This project is licensed under the MIT License - see LICENSE file for details.

---

**Last Updated:** 2025-05-08  
**Version:** 1.0.0
