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
MINIKUBE_WORKSPACE="/data/claude-workspace"

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
echo "Creating workspace configuration..."
echo "  Host workspace: $HOST_WORKSPACE"
echo "  Minikube workspace: $MINIKUBE_WORKSPACE"
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: workspace-config
  namespace: backend
data:
  DOCKER_HOST_WORKSPACE: "$HOST_WORKSPACE"
  MINIKUBE_WORKSPACE: "$MINIKUBE_WORKSPACE"
EOF

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
echo "IMPORTANT: Start the workspace mount in a separate terminal:"
echo "  ./scripts/start-workspace-mount.sh"
echo ""
echo "This mount bridges the host and Minikube filesystems so that"
echo "files created by MCP agents are visible in the pods."
echo ""
echo "To access the frontend, run:"
echo "  minikube service frontend-service -n frontend"
echo ""
echo "Or get the URL with:"
echo "  minikube service frontend-service -n frontend --url"
echo ""
echo "Check deployment status with:"
echo "  kubectl get pods -n frontend"
echo "  kubectl get pods -n backend"
echo ""
echo "View workspace files created by agents:"
echo "  ls -la $HOST_WORKSPACE"
echo "  kubectl exec -n backend deploy/orchestrator -- ls -la /workspace/"
echo ""
echo "View persistent logs with:"
echo "  ./scripts/view-logs.sh"
