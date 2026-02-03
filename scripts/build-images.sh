#!/bin/bash
set -e

# Build Docker images for the Claude Multi-Agent MCP System
# This script should be run with Minikube's Docker daemon

echo "=========================================="
echo "Building Claude Multi-Agent MCP Images"
echo "=========================================="

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Switch to Minikube's Docker daemon
echo "Configuring Docker to use Minikube's Docker daemon..."
eval $(minikube docker-env)

# Build MCP server image
echo ""
echo "Building MCP server image..."
docker build -t claude-mcp:latest "$PROJECT_ROOT/docker/mcp"

# Build frontend image
echo ""
echo "Building frontend image..."
docker build -t claude-frontend:latest "$PROJECT_ROOT/frontend"

# Build orchestrator image
echo ""
echo "Building orchestrator image..."
docker build -t claude-orchestrator:latest "$PROJECT_ROOT/backend/orchestrator"

echo ""
echo "=========================================="
echo "All images built successfully!"
echo "=========================================="
echo ""
echo "Images available in Minikube:"
docker images | grep -E "claude-(mcp|frontend|orchestrator)"
