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

# Delete frontend resources
echo ""
echo "Deleting frontend resources..."
kubectl delete -f "$K8S_DIR/frontend/" --ignore-not-found=true

# Delete backend resources
echo ""
echo "Deleting backend resources..."
kubectl delete -f "$K8S_DIR/backend/" --ignore-not-found=true

# Delete namespaces (this will delete all remaining resources in them)
echo ""
echo "Deleting namespaces..."
kubectl delete namespace frontend --ignore-not-found=true
kubectl delete namespace backend --ignore-not-found=true

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
