#!/bin/bash
set -e

# Start the workspace mount for sharing files between host, pods, and docker containers
# This script MUST be running for workspace persistence to work with Minikube Docker driver

echo "=========================================="
echo "Starting Minikube Workspace Mount"
echo "=========================================="

# Configuration
HOST_WORKSPACE="${HOST_WORKSPACE:-$HOME/claude-workspace}"
MINIKUBE_WORKSPACE="/mnt/claude-workspace"

# Create host workspace directory
echo "Creating host workspace directory: $HOST_WORKSPACE"
mkdir -p "$HOST_WORKSPACE"

echo ""
echo "IMPORTANT: This mount must stay running for workspace persistence!"
echo "Keep this terminal open or run in background with: nohup ./scripts/start-workspace-mount.sh &"
echo ""
echo "Workspace locations:"
echo "  - Host: $HOST_WORKSPACE"
echo "  - Minikube: $MINIKUBE_WORKSPACE"
echo "  - Pods: /workspace"
echo ""
echo "Starting mount (Ctrl+C to stop)..."
echo "=========================================="

# Start the mount - this blocks and must stay running
minikube mount "$HOST_WORKSPACE:$MINIKUBE_WORKSPACE"
