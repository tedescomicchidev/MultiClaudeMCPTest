# Claude Multi-Agent MCP System

A Kubernetes-based solution for running multiple Claude agents via the Model Context Protocol (MCP) on Minikube.

## Architecture

```
                                    Minikube Cluster
    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ┌─────────────────────────────────────────────────────────┐   │
    │   │                  Frontend Namespace                      │   │
    │   │  ┌─────────────────────────────────────────────────┐    │   │
    │   │  │            Frontend (Flask)                      │    │   │
    │   │  │  - Web UI for prompt input                       │    │   │
    │   │  │  - Agent count selector                          │    │   │
    │   │  │  - Results display                               │    │   │
    │   │  └─────────────────────────────────────────────────┘    │   │
    │   └─────────────────────────────────────────────────────────┘   │
    │                              │                                   │
    │                              ▼                                   │
    │   ┌─────────────────────────────────────────────────────────┐   │
    │   │                  Backend Namespace                       │   │
    │   │  ┌─────────────────────────────────────────────────┐    │   │
    │   │  │      Orchestrator (2 replicas, load balanced)    │    │   │
    │   │  │  - Receives prompts from frontend                │    │   │
    │   │  │  - Spawns Claude agents via Agent SDK            │    │   │
    │   │  │  - Manages MCP server connections                │    │   │
    │   │  └─────────────────────────────────────────────────┘    │   │
    │   │                          │                               │   │
    │   │                          ▼                               │   │
    │   │  ┌─────────────────────────────────────────────────┐    │   │
    │   │  │           Claude MCP Server                      │    │   │
    │   │  │  - Runs Claude Code CLI                          │    │   │
    │   │  │  - Processes agent requests                      │    │   │
    │   │  │  - Executes MCP commands                         │    │   │
    │   │  └─────────────────────────────────────────────────┘    │   │
    │   └─────────────────────────────────────────────────────────┘   │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

## Components

### Frontend (frontend namespace)
- **Technology**: Python Flask web application
- **Purpose**: Provides a web interface for users to:
  - Enter prompts for Claude agents
  - Select the number of agents (1-10)
  - View results from agent execution
- **Port**: 5000 (internal), 30080 (NodePort)

### Backend (backend namespace)

#### Orchestrator
- **Technology**: Python Flask with Claude Agent SDK
- **Purpose**:
  - Receives requests from the frontend
  - Spawns multiple Claude agents concurrently
  - Manages MCP server communication
- **Replicas**: 2 (load balanced)
- **Port**: 8080

#### Claude MCP Server
- **Technology**: Alpine Linux with Claude Code CLI
- **Purpose**:
  - Provides MCP server capabilities
  - Runs in background with interactive mode
  - Processes agent tool calls

## Prerequisites

- macOS with Minikube installed
- Docker (can use Minikube's Docker daemon)
- kubectl configured
- Anthropic API key

## Quick Start

### 1. Start Minikube

```bash
minikube start --driver=docker
```

### 2. Set Environment Variables

```bash
export ANTHROPIC_API_KEY='your-anthropic-api-key'
```

### 3. Build Docker Images

```bash
./scripts/build-images.sh
```

### 4. Deploy to Minikube

```bash
./scripts/deploy.sh
```

### 5. Access the Application

```bash
minikube service frontend-service -n frontend
```

Or get the URL:
```bash
minikube service frontend-service -n frontend --url
```

## Project Structure

```
.
├── README.md
├── frontend/
│   ├── Dockerfile
│   ├── app.py              # Flask application
│   ├── requirements.txt
│   └── templates/
│       └── index.html      # Web UI
├── backend/
│   └── orchestrator/
│       ├── Dockerfile
│       ├── app.py          # Orchestrator application
│       ├── requirements.txt
│       └── mcp_settings.json
├── docker/
│   └── mcp/
│       └── Dockerfile      # MCP server image
├── kubernetes/
│   ├── namespaces/
│   │   └── namespaces.yaml
│   ├── frontend/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── backend/
│       ├── orchestrator-deployment.yaml
│       ├── orchestrator-service.yaml
│       ├── mcp-server-deployment.yaml
│       ├── configmap.yaml
│       ├── secret.yaml
│       └── logs-pvc.yaml      # Persistent volume for logs
└── scripts/
    ├── build-images.sh
    ├── deploy.sh
    ├── cleanup.sh
    └── view-logs.sh           # Log viewer utility
```

## Usage

1. Open the frontend in your browser
2. Enter a prompt describing what you want the agents to do
3. Select the number of agents (1-10)
4. Click "GO - Launch Agents"
5. Wait for the results to appear

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Required |
| `ORCHESTRATOR_URL` | Backend orchestrator URL | `http://orchestrator-service.backend.svc.cluster.local:8080` |
| `WORKSPACE_PATH` | Workspace path for MCP | `/workspace` |
| `DOCKER_MCP_IMAGE` | MCP Docker image name | `claude-mcp:latest` |

### Scaling

To scale the orchestrator:
```bash
kubectl scale deployment orchestrator -n backend --replicas=4
```

## Persistent Logging

Errors and exceptions are persisted in a PersistentVolume so you can investigate issues even after pod restarts.

### Log Locations

| Component | Log Path | Description |
|-----------|----------|-------------|
| Orchestrator | `/var/log/orchestrator/orchestrator.log` | All logs (DEBUG level) |
| Orchestrator | `/var/log/orchestrator/orchestrator-errors.log` | Errors only |
| MCP Server | `/var/log/mcp-server/mcp-server.log` | Server activity logs |

### View Logs with Helper Script

```bash
# View all logs
./scripts/view-logs.sh

# View orchestrator logs only
./scripts/view-logs.sh --orchestrator

# View only error logs
./scripts/view-logs.sh --orchestrator-errors

# View MCP server logs
./scripts/view-logs.sh --mcp

# Follow logs in real-time
./scripts/view-logs.sh --tail --orchestrator

# List all log files
./scripts/view-logs.sh --list
```

### Manual Log Access

```bash
# List orchestrator log files
kubectl exec -n backend deploy/orchestrator -- ls -la /var/log/orchestrator/

# View orchestrator logs
kubectl exec -n backend deploy/orchestrator -- cat /var/log/orchestrator/orchestrator.log

# View orchestrator error logs
kubectl exec -n backend deploy/orchestrator -- cat /var/log/orchestrator/orchestrator-errors.log

# Follow orchestrator logs
kubectl exec -n backend deploy/orchestrator -- tail -f /var/log/orchestrator/orchestrator.log

# View MCP server logs
kubectl exec -n backend deploy/claude-mcp-server -- cat /var/log/mcp-server/mcp-server.log
```

### Log Retention

- Logs are stored in a 1GB PersistentVolumeClaim
- Log files rotate at 10MB with 5 backups kept
- Logs persist across pod restarts and redeployments

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n frontend
kubectl get pods -n backend
```

### View Container Logs (stdout/stderr)
```bash
# Frontend logs
kubectl logs -n frontend -l app=frontend

# Orchestrator logs
kubectl logs -n backend -l app=orchestrator

# MCP server logs
kubectl logs -n backend -l app=claude-mcp-server
```

### View Persistent Error Logs
```bash
# Quick error investigation
./scripts/view-logs.sh --orchestrator-errors
```

### Restart Deployments
```bash
kubectl rollout restart deployment frontend -n frontend
kubectl rollout restart deployment orchestrator -n backend
kubectl rollout restart deployment claude-mcp-server -n backend
```

## Cleanup

```bash
./scripts/cleanup.sh
```

## Security Notes

- The API key is stored as a Kubernetes secret
- The MCP server runs in a sandboxed environment (`IS_SANDBOX=1`)
- The orchestrator mounts the Docker socket - ensure proper security policies

## License

MIT
