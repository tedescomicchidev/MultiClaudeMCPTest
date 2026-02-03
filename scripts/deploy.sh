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

# Create PersistentVolumeClaim for logs
echo ""
echo "Creating PersistentVolumeClaim for logs..."
kubectl apply -f "$K8S_DIR/backend/logs-pvc.yaml"

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
echo "View persistent logs with:"
echo "  ./scripts/view-logs.sh"
echo ""
echo "Or manually access logs:"
echo "  kubectl exec -n backend deploy/orchestrator -- ls -la /var/log/orchestrator/"
echo "  kubectl exec -n backend deploy/orchestrator -- cat /var/log/orchestrator/orchestrator.log"
echo "  kubectl exec -n backend deploy/orchestrator -- cat /var/log/orchestrator/orchestrator-errors.log"
