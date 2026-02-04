FROM alpine:latest

# Install packages
RUN apk update && apk add --no-cache \
    bash \
    curl \
    git \
    build-base \
    python3 \
    py3-pip \
    nodejs \
    npm \
    vim \
    coreutils

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Create log directory
RUN mkdir -p /var/log/claude-mcp

# Create wrapper script for MCP server with logging
RUN cat > /usr/local/bin/claude-mcp-serve.sh << 'EOF'
#!/bin/bash
set -e

LOG_DIR="${LOG_DIR:-/var/log/claude-mcp}"
LOG_FILE="${LOG_DIR}/mcp-serve-$(date +%Y%m%d-%H%M%S).log"
ERROR_LOG="${LOG_DIR}/mcp-serve-errors.log"

mkdir -p "$LOG_DIR"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting Claude MCP Server" | tee -a "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') - Workspace: $(pwd)" | tee -a "$LOG_FILE"

# Run claude mcp serve with logging
# For stdio mode, we need to be careful not to interfere with stdin/stdout
# So we only log to stderr which gets captured
exec claude mcp serve 2> >(tee -a "$ERROR_LOG" "$LOG_FILE" >&2)
EOF

RUN chmod +x /usr/local/bin/claude-mcp-serve.sh

# Set up working directory
WORKDIR /workspace

# Env
ENV IS_SANDBOX=1
ENV LOG_DIR=/var/log/claude-mcp

# Expose port for stdio communication (not strictly needed for stdio)
# But useful if you want to add HTTP/SSE transport later

# Default command - run as MCP server with logging
CMD ["claude", "mcp", "serve"]
