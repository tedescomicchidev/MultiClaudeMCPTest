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
    vim

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Set up working directory
WORKDIR /workspace

# Env
ENV IS_SANDBOX=1

# Expose port for stdio communication (not strictly needed for stdio)
# But useful if you want to add HTTP/SSE transport later

# Default command - run as MCP server
CMD ["claude", "mcp", "serve"]
