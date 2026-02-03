#!/bin/bash

# View persistent logs from orchestrator and MCP server containers
# Logs are stored in PersistentVolume and survive pod restarts

set -e

NAMESPACE="backend"

echo "=========================================="
echo "Claude Multi-Agent MCP System - Log Viewer"
echo "=========================================="

show_help() {
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  --orchestrator, -o     Show orchestrator logs"
    echo "  --orchestrator-errors  Show orchestrator error logs only"
    echo "  --mcp, -m              Show MCP server logs"
    echo "  --all, -a              Show all logs (default)"
    echo "  --tail, -t             Follow logs (like tail -f)"
    echo "  --list, -l             List all log files"
    echo "  --help, -h             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --orchestrator        # View orchestrator logs"
    echo "  $0 --orchestrator-errors # View only error logs"
    echo "  $0 --tail -o             # Follow orchestrator logs"
    echo "  $0 --list                # List all log files"
    echo ""
}

list_logs() {
    echo ""
    echo "=== Orchestrator Log Files ==="
    kubectl exec -n $NAMESPACE deploy/orchestrator -- find /var/log/orchestrator -type f -name "*.log" 2>/dev/null || echo "No orchestrator logs found"

    echo ""
    echo "=== MCP Server Log Files ==="
    kubectl exec -n $NAMESPACE deploy/claude-mcp-server -- find /var/log/mcp-server -type f -name "*.log" 2>/dev/null || echo "No MCP server logs found"
}

view_orchestrator_logs() {
    local follow=$1
    echo ""
    echo "=== Orchestrator Logs ==="
    echo ""

    if [ "$follow" = "true" ]; then
        kubectl exec -n $NAMESPACE deploy/orchestrator -- tail -f /var/log/orchestrator/orchestrator.log 2>/dev/null || \
        kubectl logs -n $NAMESPACE deploy/orchestrator -f
    else
        kubectl exec -n $NAMESPACE deploy/orchestrator -- cat /var/log/orchestrator/orchestrator.log 2>/dev/null || \
        echo "No persistent logs found. Showing container logs:"
        kubectl logs -n $NAMESPACE deploy/orchestrator --tail=100
    fi
}

view_orchestrator_errors() {
    echo ""
    echo "=== Orchestrator Error Logs ==="
    echo ""
    kubectl exec -n $NAMESPACE deploy/orchestrator -- cat /var/log/orchestrator/orchestrator-errors.log 2>/dev/null || \
    echo "No error logs found"
}

view_mcp_logs() {
    local follow=$1
    echo ""
    echo "=== MCP Server Logs ==="
    echo ""

    if [ "$follow" = "true" ]; then
        kubectl exec -n $NAMESPACE deploy/claude-mcp-server -- tail -f /var/log/mcp-server/mcp-server.log 2>/dev/null || \
        kubectl logs -n $NAMESPACE deploy/claude-mcp-server -f
    else
        kubectl exec -n $NAMESPACE deploy/claude-mcp-server -- cat /var/log/mcp-server/mcp-server.log 2>/dev/null || \
        echo "No persistent logs found. Showing container logs:"
        kubectl logs -n $NAMESPACE deploy/claude-mcp-server --tail=100
    fi
}

# Parse arguments
FOLLOW="false"
VIEW_ORCH="false"
VIEW_ORCH_ERRORS="false"
VIEW_MCP="false"
VIEW_ALL="true"
LIST_ONLY="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        --orchestrator|-o)
            VIEW_ORCH="true"
            VIEW_ALL="false"
            shift
            ;;
        --orchestrator-errors)
            VIEW_ORCH_ERRORS="true"
            VIEW_ALL="false"
            shift
            ;;
        --mcp|-m)
            VIEW_MCP="true"
            VIEW_ALL="false"
            shift
            ;;
        --all|-a)
            VIEW_ALL="true"
            shift
            ;;
        --tail|-t)
            FOLLOW="true"
            shift
            ;;
        --list|-l)
            LIST_ONLY="true"
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Execute based on options
if [ "$LIST_ONLY" = "true" ]; then
    list_logs
    exit 0
fi

if [ "$VIEW_ORCH" = "true" ]; then
    view_orchestrator_logs $FOLLOW
fi

if [ "$VIEW_ORCH_ERRORS" = "true" ]; then
    view_orchestrator_errors
fi

if [ "$VIEW_MCP" = "true" ]; then
    view_mcp_logs $FOLLOW
fi

if [ "$VIEW_ALL" = "true" ]; then
    view_orchestrator_logs $FOLLOW
    echo ""
    echo "----------------------------------------"
    view_orchestrator_errors
    echo ""
    echo "----------------------------------------"
    view_mcp_logs $FOLLOW
fi

echo ""
echo "=========================================="
echo "End of logs"
echo "=========================================="
