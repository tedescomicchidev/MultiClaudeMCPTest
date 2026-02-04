#!/bin/bash
set -e

# Cleanup Claude Multi-Agent MCP System from Minikube

echo "=========================================="
echo "Cleaning up Claude Multi-Agent MCP System"
echo "=========================================="

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$PROJECT_ROOT/kubernetes"

# Workspace configuration (for cleanup info)
HOST_WORKSPACE="${HOST_WORKSPACE:-$HOME/claude-workspace}"
MINIKUBE_WORKSPACE="/mnt/claude-workspace"

# Delete frontend resources
echo ""
echo "Deleting frontend resources..."
kubectl delete -f "$K8S_DIR/frontend/" --ignore-not-found=true 2>/dev/null || true

# Delete backend resources (deployments, services, etc.)
echo ""
echo "Deleting backend deployments and services..."
kubectl delete deployment orchestrator -n backend --ignore-not-found=true 2>/dev/null || true
kubectl delete deployment claude-mcp-server -n backend --ignore-not-found=true 2>/dev/null || true
kubectl delete service orchestrator-service -n backend --ignore-not-found=true 2>/dev/null || true

# Delete ConfigMaps
echo ""
echo "Deleting ConfigMaps..."
kubectl delete configmap workspace-config -n backend --ignore-not-found=true 2>/dev/null || true
kubectl delete configmap mcp-settings -n backend --ignore-not-found=true 2>/dev/null || true

# Delete Secrets
echo ""
echo "Deleting Secrets..."
kubectl delete secret anthropic-api-key -n backend --ignore-not-found=true 2>/dev/null || true

# Delete PVCs
echo ""
echo "Deleting PersistentVolumeClaims..."
kubectl delete pvc backend-logs-pvc -n backend --ignore-not-found=true 2>/dev/null || true
kubectl delete pvc agent-workspace-pvc -n backend --ignore-not-found=true 2>/dev/null || true

# Delete any remaining backend resources from manifests
echo ""
echo "Deleting remaining backend resources..."
kubectl delete -f "$K8S_DIR/backend/" --ignore-not-found=true 2>/dev/null || true

# Delete namespaces (this will delete all remaining resources in them)
echo ""
echo "Deleting namespaces..."
kubectl delete namespace frontend --ignore-not-found=true 2>/dev/null || true
kubectl delete namespace backend --ignore-not-found=true 2>/dev/null || true

# Clean up Minikube workspace directory
echo ""
echo "Cleaning up Minikube workspace directory..."
minikube ssh "sudo rm -rf $MINIKUBE_WORKSPACE" 2>/dev/null || true

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
echo ""
echo "Note: The following are NOT deleted (manual cleanup if needed):"
echo "  - Host workspace: $HOST_WORKSPACE"
echo "  - Docker images: claude-mcp:latest, claude-orchestrator:latest, claude-frontend:latest"
echo ""
echo "To remove Docker images:"
echo "  eval \$(minikube docker-env)"
echo "  docker rmi claude-mcp:latest claude-orchestrator:latest claude-frontend:latest"
echo ""
echo "To remove host workspace:"
echo "  rm -rf $HOST_WORKSPACE"
echo ""
echo "Don't forget to stop the minikube mount process if it's running!"
