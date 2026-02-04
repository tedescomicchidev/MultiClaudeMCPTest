# Multi-Agent Claude MCP System on Minikube

## Overview

A Kubernetes-based system for running multiple Claude agents via MCP (Model Context Protocol) on Minikube. The system consists of a Python frontend, a Python orchestrator backend, and MCP containers running Claude Code CLI.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Minikube Cluster                            │
│                                                                          │
│  ┌─────────────────────────────┐    ┌─────────────────────────────────┐ │
│  │     Frontend Namespace      │    │       Backend Namespace          │ │
│  │                             │    │                                   │ │
│  │  ┌───────────────────────┐  │    │  ┌─────────────────────────────┐ │ │
│  │  │   Flask Web App       │  │    │  │   Orchestrator (2 replicas) │ │ │
│  │  │   - User prompt input │──┼────┼──│   - claude-agent-sdk        │ │ │
│  │  │   - Agent count slider│  │    │  │   - Git workflow manager    │ │ │
│  │  │   - Results display   │  │    │  │   - Docker CLI              │ │ │
│  │  └───────────────────────┘  │    │  └──────────────┬──────────────┘ │ │
│  │                             │    │                 │                 │ │
│  └─────────────────────────────┘    │                 │ docker run     │ │
│                                     │                 ▼                 │ │
│                                     │  ┌─────────────────────────────┐ │ │
│                                     │  │   MCP Containers            │ │ │
│                                     │  │   (claude-code-docker)      │ │ │
│                                     │  │   - One per agent           │ │ │
│                                     │  │   - Isolated worktrees      │ │ │
│                                     │  └─────────────────────────────┘ │ │
│                                     │                                   │ │
│                                     └───────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Persistent Storage                             │   │
│  │  /data/claude-workspace (hostPath via minikube mount)            │   │
│  │  └── runs/                                                        │   │
│  │      └── run_<timestamp>_<uuid>/                                  │   │
│  │          ├── .git/                                                │   │
│  │          ├── README.md                                            │   │
│  │          └── worktrees/                                           │   │
│  │              ├── agent-1/ (branch: agent-1)                       │   │
│  │              └── agent-2/ (branch: agent-2)                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Frontend (Python Flask)

**Namespace:** `frontend`

**Features:**
- Web UI for entering prompts
- Slider to select number of agents (1-10)
- Displays results from each agent
- Shows run info (run_id, git status)

**Endpoints:**
- `GET /` - Main UI
- `POST /submit` - Submit prompt to orchestrator

### 2. Backend Orchestrator (Python Flask + Gunicorn)

**Namespace:** `backend`

**Features:**
- Receives prompts from frontend
- Creates git repository for each run
- Creates git worktree per agent for isolation
- Spawns Claude agents via `claude-agent-sdk`
- Adds commit instructions to agent prompts
- Persistent logging with rotation

**Key Endpoints:**
- `POST /orchestrate` - Main orchestration endpoint
- `GET /health` - Health check for K8s probes
- `GET /ready` - Readiness check
- `GET /diagnostics` - Docker and system diagnostics
- `GET /test-docker` - Test Docker connectivity
- `GET /workspace` - List workspace files
- `GET /workspace/<path>` - Get file contents

**Configuration (Environment Variables):**
```yaml
ANTHROPIC_API_KEY: API key for Claude
WORKSPACE_PATH: /data/claude-workspace  # Docker host path for -v mount
WORKSPACE_LOCAL: /workspace              # Path inside orchestrator container
DOCKER_MCP_IMAGE: claude-mcp:latest     # MCP container image
LOG_DIR: /var/log/orchestrator          # Persistent log directory
LOG_LEVEL: INFO                         # Logging level
```

### 3. MCP Container (claude-code-docker)

**Features:**
- Runs Claude Code CLI in MCP server mode
- Spawned dynamically via `docker run` from orchestrator
- Each agent gets isolated workspace (git worktree)
- Mounts workspace volume for file persistence

**Docker Run Command:**
```bash
docker run -i --rm \
  -v /data/claude-workspace/runs/<run_id>/worktrees/agent-<N>:/workspace \
  claude-mcp:latest \
  claude mcp serve
```

## Git Workflow

When the orchestrator receives a prompt:

1. **Create Run Directory**
   - Generates unique run ID: `<timestamp>_<uuid>`
   - Creates `/workspace/runs/run_<id>/`

2. **Initialize Git Repository**
   - Runs `git init` in run directory
   - Configures git user (agent@claude-mcp.local)
   - Creates initial commit with README

3. **Create Agent Worktrees**
   - For each agent, creates a branch (`agent-1`, `agent-2`, etc.)
   - Creates git worktree in `worktrees/agent-<N>/`
   - Each agent works in isolated worktree

4. **Enhance Agent Prompts**
   - Adds system instructions to commit changes
   - Includes branch name and workspace path
   - Instructs agent to `git add -A && git commit` at end

**Example Enhanced Prompt:**
```markdown
## IMPORTANT: Workspace and Git Instructions

You are Agent 1 working on branch `agent-1`.

**Your working directory is: /workspace**

All files you create should be placed in /workspace.

**CRITICAL: At the end of your work, you MUST commit all your changes:**

1. Stage all your changes:
   ```bash
   git add -A
   ```

2. Commit with a descriptive message:
   ```bash
   git commit -m "Agent 1: <brief description of what you implemented>"
   ```

---

## Your Task:

<original user prompt>
```

## Logging

### Log Locations

| Log Type | Path | Level | Purpose |
|----------|------|-------|---------|
| Main log | `/var/log/orchestrator/orchestrator.log` | DEBUG+ | All application logs |
| Error log | `/var/log/orchestrator/orchestrator-errors.log` | ERROR only | Quick error investigation |
| Container stdout | `kubectl logs` | INFO+ | Real-time monitoring |

### Viewing Logs

```bash
# View all logs
./scripts/view-logs.sh

# View error logs only
./scripts/view-logs.sh --orchestrator-errors

# View container stdout/stderr
./scripts/view-logs.sh --container

# Follow logs in real-time
./scripts/view-logs.sh --tail -o

# Show last N lines
./scripts/view-logs.sh --last 50 -o
```

### Gunicorn Configuration

The orchestrator runs under Gunicorn with these logging flags:
- `--capture-output`: Captures worker stdout/stderr
- `--access-logfile -`: Logs HTTP requests to stdout
- `--log-level info`: Sets gunicorn log level

## Workspace Persistence

### The Challenge

- Orchestrator runs inside Minikube (a VM/container)
- Docker runs on the host machine
- `docker run -v` mounts from Docker host, not from inside Minikube
- This creates a path mismatch

### The Solution: Minikube Mount

Use `minikube mount` to bridge host and Minikube filesystems:

```bash
# Terminal 1: Start the mount (keep running)
./scripts/start-workspace-mount.sh

# This runs:
minikube mount /home/user/claude-workspace:/data/claude-workspace
```

### Path Configuration

| Path | Location | Purpose |
|------|----------|---------|
| `WORKSPACE_PATH` | `/data/claude-workspace` | Used in `docker run -v` (Minikube internal) |
| `WORKSPACE_LOCAL` | `/workspace` | Mounted inside orchestrator pod |
| Host path | `/home/user/claude-workspace` | Actual files on your machine |

## Kubernetes Resources

### Backend Namespace

```yaml
# Orchestrator Deployment
- 2 replicas (load balanced)
- Memory: 512Mi-2Gi
- CPU: 250m-1000m
- Mounts: Docker socket, workspace, logs PVC

# Services
- orchestrator-service: ClusterIP on port 8080

# ConfigMaps
- workspace-config: Contains WORKSPACE_PATH

# Secrets
- anthropic-api-key: ANTHROPIC_API_KEY

# PVCs
- orchestrator-logs: 1Gi for persistent logs
```

### Frontend Namespace

```yaml
# Frontend Deployment
- 2 replicas
- Flask web application

# Services
- frontend-service: NodePort for external access
```

## Deployment

### Prerequisites

1. Minikube running with Docker driver
2. Docker installed on host
3. Anthropic API key

### Deploy Steps

```bash
# 1. Build Docker images
docker build -t orchestrator:latest ./backend/orchestrator/
docker build -t frontend:latest ./frontend/

# 2. Load images into Minikube
minikube image load orchestrator:latest
minikube image load frontend:latest

# 3. Start workspace mount (keep terminal open)
./scripts/start-workspace-mount.sh

# 4. Deploy to Kubernetes
./scripts/deploy.sh

# 5. Access the frontend
minikube service frontend-service -n frontend
```

### Cleanup

```bash
./scripts/cleanup.sh
```

## API Response Format

### POST /orchestrate

**Request:**
```json
{
  "prompt": "Build a typescript app which shows a digital clock.",
  "agent_count": 2
}
```

**Response:**
```json
{
  "status": "completed",
  "run_info": {
    "run_id": "20260204_123456_abc12345",
    "run_dir": "runs/run_20260204_123456_abc12345",
    "git_initialized": true
  },
  "summary": {
    "total_agents": 2,
    "successful": 2,
    "failed": 0
  },
  "results": [
    {
      "agent_id": 1,
      "status": "success",
      "output": "I've created the digital clock app...",
      "workspace": {
        "worktree_path": "runs/run_20260204_123456_abc12345/worktrees/agent-1",
        "branch_name": "agent-1"
      },
      "messages": []
    },
    {
      "agent_id": 2,
      "status": "success",
      "output": "I've implemented the clock...",
      "workspace": {
        "worktree_path": "runs/run_20260204_123456_abc12345/worktrees/agent-2",
        "branch_name": "agent-2"
      },
      "messages": []
    }
  ]
}
```

## Troubleshooting

### Common Issues

1. **"No such file or directory: 'git'"**
   - Git not installed in orchestrator container
   - Rebuild with updated Dockerfile that includes `git`

2. **"API Error: 500 Internal server error"**
   - Transient error from Anthropic's API
   - Retry the request
   - Check Anthropic status page

3. **"Docker is not available"**
   - Docker socket not mounted
   - Check `/var/run/docker.sock` mount in deployment

4. **"MCP image not found"**
   - Build and load the MCP image: `minikube image load claude-mcp:latest`

5. **Files not persisting**
   - Ensure `minikube mount` is running
   - Check workspace-config ConfigMap has correct path

### Diagnostic Commands

```bash
# Check pod status
kubectl get pods -n backend

# Check orchestrator diagnostics
kubectl exec -n backend deploy/orchestrator -- curl -s localhost:8080/diagnostics | jq

# Test Docker connectivity
kubectl exec -n backend deploy/orchestrator -- curl -s localhost:8080/test-docker | jq

# List workspace files
kubectl exec -n backend deploy/orchestrator -- curl -s localhost:8080/workspace | jq

# View error logs
./scripts/view-logs.sh --orchestrator-errors
```

## Dependencies

### Orchestrator (requirements.txt)
```
flask>=3.0.0
gunicorn>=21.0.0
claude-agent-sdk>=0.1.0
```

### System Dependencies (Dockerfile)
- Python 3.11
- Docker CLI
- Git
- curl

## File Structure

```
MultiClaudeMCPTest/
├── backend/
│   └── orchestrator/
│       ├── app.py              # Main orchestrator application
│       ├── Dockerfile          # Container build
│       ├── requirements.txt    # Python dependencies
│       └── mcp_settings.json   # MCP configuration
├── frontend/
│   ├── app.py                  # Flask web UI
│   ├── Dockerfile
│   ├── requirements.txt
│   └── templates/
│       └── index.html          # Web interface
├── kubernetes/
│   ├── backend/
│   │   ├── namespace.yaml
│   │   ├── orchestrator-deployment.yaml
│   │   ├── orchestrator-service.yaml
│   │   └── orchestrator-pvc.yaml
│   └── frontend/
│       ├── namespace.yaml
│       ├── frontend-deployment.yaml
│       └── frontend-service.yaml
├── scripts/
│   ├── deploy.sh               # Deploy all resources
│   ├── cleanup.sh              # Remove all resources
│   ├── start-workspace-mount.sh # Start minikube mount
│   └── view-logs.sh            # Log viewer utility
└── SYSTEM_DESIGN.md            # This document
```
