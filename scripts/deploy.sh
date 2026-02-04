#!/bin/bash
set -e

# Deploy Claude Multi-Agent MCP System to Minikube
# Prerequisites: minikube running, images built

echo "=========================================="
echo "Deploying Claude Multi-Agent MCP System"
echo "=========================================="

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$PROJECT_ROOT/kubernetes"

# Workspace configuration
# HOST_WORKSPACE: Path on your actual machine (Mac/Linux) - used by docker run -v
# MINIKUBE_WORKSPACE: Path inside Minikube VM - used by pod hostPath
HOST_WORKSPACE="${HOST_WORKSPACE:-$HOME/claude-workspace}"
MINIKUBE_WORKSPACE="/mnt/claude-workspace"

echo ""
echo "Configuration:"
echo "  HOST_WORKSPACE: $HOST_WORKSPACE"
echo "  MINIKUBE_WORKSPACE: $MINIKUBE_WORKSPACE"
echo ""
echo "To use a different host workspace, set HOST_WORKSPACE before running:"
echo "  HOST_WORKSPACE=/path/to/workspace ./scripts/deploy.sh"
echo ""

# Check if minikube is running
if ! minikube status | grep -q "Running"; then
    echo "Error: Minikube is not running. Please start it with 'minikube start'"
    exit 1
fi

# Check if ANTHROPIC_API_KEY is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY environment variable is not set"
    echo "Please set it with: export ANTHROPIC_API_KEY='your-api-key'"
    exit 1
fi

# Create host workspace directory
echo ""
echo "Creating host workspace directory: $HOST_WORKSPACE"
mkdir -p "$HOST_WORKSPACE"

# Create namespaces
echo ""
echo "Creating namespaces..."
kubectl apply -f "$K8S_DIR/namespaces/namespaces.yaml"

# Create secret with API key
echo ""
echo "Creating Anthropic API key secret..."
kubectl create secret generic anthropic-api-key \
    --namespace=backend \
    --from-literal=api-key="$ANTHROPIC_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -

# Create ConfigMap for MCP settings
echo ""
echo "Creating MCP settings ConfigMap..."
kubectl apply -f "$K8S_DIR/backend/configmap.yaml"

# Create workspace config with the correct host path
echo ""
echo "Creating workspace configuration ConfigMap..."
echo "  DOCKER_HOST_WORKSPACE: $HOST_WORKSPACE"
echo "  MINIKUBE_WORKSPACE: $MINIKUBE_WORKSPACE"
kubectl create configmap workspace-config \
    --namespace=backend \
    --from-literal=DOCKER_HOST_WORKSPACE="$HOST_WORKSPACE" \
    --from-literal=MINIKUBE_WORKSPACE="$MINIKUBE_WORKSPACE" \
    --dry-run=client -o yaml | kubectl apply -f -

# Create PersistentVolumeClaim for logs
echo ""
echo "Creating PersistentVolumeClaim for logs..."
kubectl apply -f "$K8S_DIR/backend/logs-pvc.yaml"

# Create workspace directory on Minikube node
echo ""
echo "Creating workspace directory on Minikube node..."
minikube ssh "sudo mkdir -p $MINIKUBE_WORKSPACE && sudo chmod 777 $MINIKUBE_WORKSPACE"

# Deploy MCP server
echo ""
echo "Deploying MCP server..."
kubectl apply -f "$K8S_DIR/backend/mcp-server-deployment.yaml"

# Deploy orchestrator
echo ""
echo "Deploying orchestrator..."
kubectl apply -f "$K8S_DIR/backend/orchestrator-deployment.yaml"
kubectl apply -f "$K8S_DIR/backend/orchestrator-service.yaml"

# Deploy frontend
echo ""
echo "Deploying frontend..."
kubectl apply -f "$K8S_DIR/frontend/deployment.yaml"
kubectl apply -f "$K8S_DIR/frontend/service.yaml"

# Wait for deployments
echo ""
echo "Waiting for deployments to be ready..."
kubectl rollout status deployment/claude-mcp-server -n backend --timeout=120s || true
kubectl rollout status deployment/orchestrator -n backend --timeout=120s || true
kubectl rollout status deployment/frontend -n frontend --timeout=120s || true

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  IMPORTANT: Start the workspace mount in a SEPARATE terminal!   ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "Run this command and KEEP IT RUNNING:"
echo ""
echo "  minikube mount $HOST_WORKSPACE:$MINIKUBE_WORKSPACE"
echo ""
echo "Or use the helper script:"
echo "  HOST_WORKSPACE=$HOST_WORKSPACE ./scripts/start-workspace-mount.sh"
echo ""
echo "This mount bridges the host and Minikube filesystems so that"
echo "files created by MCP agents are visible in the pods."
echo ""
echo "=========================================="
echo ""
echo "To access the frontend:"
echo "  minikube service frontend-service -n frontend"
echo ""
echo "Check deployment status:"
echo "  kubectl get pods -n frontend"
echo "  kubectl get pods -n backend"
echo ""
echo "Verify workspace config:"
echo "  kubectl get configmap workspace-config -n backend -o yaml"
echo "  kubectl exec -n backend deploy/orchestrator -- env | grep WORKSPACE"
echo ""
echo "View workspace files created by agents:"
echo "  ls -la $HOST_WORKSPACE"
echo "  kubectl exec -n backend deploy/orchestrator -- ls -la /workspace/"
echo ""
echo "View logs:"
echo "  ./scripts/view-logs.sh"
