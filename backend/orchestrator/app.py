"""
Backend Orchestrator for Claude Multi-Agent MCP System.
Receives prompts from frontend and spawns multiple Claude agents via MCP.
"""

import asyncio
import os
import json
import logging
import traceback
import sys
import subprocess
import shutil
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import List, Dict, Any, Tuple
from flask import Flask, request, jsonify
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

# Configuration
LOG_DIR = os.getenv("LOG_DIR", "/var/log/orchestrator")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging with both console and file handlers
def setup_logging():
    """Setup logging with file persistence and rotation."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # Console handler - use stderr for gunicorn compatibility
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # Also hook into gunicorn's logger if available
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        root_logger.handlers = gunicorn_logger.handlers
        root_logger.setLevel(gunicorn_logger.level)

    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'orchestrator.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    # Error-specific file handler for easy error investigation
    error_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, 'orchestrator-errors.log'),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(error_handler)

    return logging.getLogger(__name__)

logger = setup_logging()

app = Flask(__name__)

# Configuration from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# WORKSPACE_PATH is the path on the Docker host (Minikube node) used for docker run -v
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", "/mnt/claude-workspace")
# WORKSPACE_LOCAL is where the workspace is mounted inside this container
WORKSPACE_LOCAL = os.getenv("WORKSPACE_LOCAL", "/workspace")
DOCKER_MCP_IMAGE = os.getenv("DOCKER_MCP_IMAGE", "claude-mcp:latest")


def check_docker_available() -> Dict[str, Any]:
    """Check if Docker is available and accessible."""
    result = {
        "docker_cli": False,
        "docker_socket": False,
        "docker_running": False,
        "mcp_image_exists": False,
        "errors": []
    }

    # Check if docker CLI exists
    docker_path = shutil.which("docker")
    result["docker_cli"] = docker_path is not None
    result["docker_cli_path"] = docker_path

    # Check if Docker socket exists
    socket_path = "/var/run/docker.sock"
    result["docker_socket"] = os.path.exists(socket_path)
    result["docker_socket_path"] = socket_path

    # Try to run docker info
    if result["docker_cli"]:
        try:
            proc = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10
            )
            result["docker_running"] = proc.returncode == 0
            if proc.returncode != 0:
                result["errors"].append(f"docker info failed: {proc.stderr}")
        except subprocess.TimeoutExpired:
            result["errors"].append("docker info timed out")
        except Exception as e:
            result["errors"].append(f"docker info error: {str(e)}")

    # Check if MCP image exists
    if result["docker_running"]:
        try:
            proc = subprocess.run(
                ["docker", "images", "-q", DOCKER_MCP_IMAGE],
                capture_output=True,
                text=True,
                timeout=10
            )
            result["mcp_image_exists"] = bool(proc.stdout.strip())
            result["mcp_image_name"] = DOCKER_MCP_IMAGE
            if not result["mcp_image_exists"]:
                result["errors"].append(f"MCP image '{DOCKER_MCP_IMAGE}' not found")
        except Exception as e:
            result["errors"].append(f"docker images error: {str(e)}")

    return result


def create_run_directory(run_id: str) -> str:
    """
    Create a directory for the current run.

    Args:
        run_id: Unique identifier for this run

    Returns:
        Path to the run directory (relative to workspace)
    """
    run_dir_name = f"run_{run_id}"
    run_dir_local = os.path.join(WORKSPACE_LOCAL, "runs", run_dir_name)

    # Create the directory
    os.makedirs(run_dir_local, exist_ok=True)
    logger.info(f"Created run directory: {run_dir_local}")

    return os.path.join("runs", run_dir_name)


def init_git_repo(run_dir_rel: str) -> bool:
    """
    Initialize a git repository for the run.

    Args:
        run_dir_rel: Relative path to run directory from workspace

    Returns:
        True if successful, False otherwise
    """
    run_dir_local = os.path.join(WORKSPACE_LOCAL, run_dir_rel)

    try:
        # Initialize git repo
        result = subprocess.run(
            ["git", "init"],
            cwd=run_dir_local,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.error(f"Git init failed: {result.stderr}")
            return False

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "agent@claude-mcp.local"],
            cwd=run_dir_local,
            capture_output=True,
            timeout=10
        )
        subprocess.run(
            ["git", "config", "user.name", "Claude Agent"],
            cwd=run_dir_local,
            capture_output=True,
            timeout=10
        )

        # Create initial commit
        readme_path = os.path.join(run_dir_local, "README.md")
        with open(readme_path, "w") as f:
            f.write(f"# Run {run_dir_rel}\n\nCreated at: {datetime.now().isoformat()}\n")

        subprocess.run(
            ["git", "add", "README.md"],
            cwd=run_dir_local,
            capture_output=True,
            timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=run_dir_local,
            capture_output=True,
            timeout=10
        )

        logger.info(f"Initialized git repo in {run_dir_local}")
        return True

    except Exception as e:
        logger.error(f"Error initializing git repo: {e}")
        return False


def create_agent_worktree(run_dir_rel: str, agent_id: int) -> Tuple[str, str]:
    """
    Create a git worktree and branch for an agent.

    Args:
        run_dir_rel: Relative path to run directory from workspace
        agent_id: Agent identifier

    Returns:
        Tuple of (worktree_path_rel, branch_name) relative to workspace
    """
    run_dir_local = os.path.join(WORKSPACE_LOCAL, run_dir_rel)
    branch_name = f"agent-{agent_id}"
    worktree_name = f"agent-{agent_id}"
    worktree_path_rel = os.path.join(run_dir_rel, "worktrees", worktree_name)
    worktree_path_local = os.path.join(WORKSPACE_LOCAL, worktree_path_rel)

    try:
        # Create worktrees directory
        worktrees_dir = os.path.join(run_dir_local, "worktrees")
        os.makedirs(worktrees_dir, exist_ok=True)

        # Create branch
        subprocess.run(
            ["git", "branch", branch_name],
            cwd=run_dir_local,
            capture_output=True,
            timeout=10
        )

        # Create worktree
        result = subprocess.run(
            ["git", "worktree", "add", worktree_path_local, branch_name],
            cwd=run_dir_local,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Failed to create worktree: {result.stderr}")
            # Fallback: just use a subdirectory
            os.makedirs(worktree_path_local, exist_ok=True)

        logger.info(f"Created worktree for agent {agent_id}: {worktree_path_rel} on branch {branch_name}")
        return worktree_path_rel, branch_name

    except Exception as e:
        logger.error(f"Error creating worktree for agent {agent_id}: {e}")
        # Fallback: create simple directory
        os.makedirs(worktree_path_local, exist_ok=True)
        return worktree_path_rel, branch_name


def setup_run_environment(agent_count: int) -> Dict[str, Any]:
    """
    Set up the complete run environment with git repo and worktrees.

    Args:
        agent_count: Number of agents to create worktrees for

    Returns:
        Dictionary with run information including paths and branches
    """
    # Generate unique run ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{timestamp}_{uuid.uuid4().hex[:8]}"

    # Create run directory
    run_dir_rel = create_run_directory(run_id)

    # Initialize git repo
    git_initialized = init_git_repo(run_dir_rel)

    # Create worktrees for each agent
    agent_workspaces = []
    for i in range(agent_count):
        agent_id = i + 1
        if git_initialized:
            worktree_path, branch_name = create_agent_worktree(run_dir_rel, agent_id)
        else:
            # Fallback without git
            worktree_path = os.path.join(run_dir_rel, f"agent-{agent_id}")
            os.makedirs(os.path.join(WORKSPACE_LOCAL, worktree_path), exist_ok=True)
            branch_name = f"agent-{agent_id}"

        agent_workspaces.append({
            "agent_id": agent_id,
            "worktree_path": worktree_path,
            "branch_name": branch_name,
            # Path for docker run -v (host path)
            "docker_path": os.path.join(WORKSPACE_PATH, worktree_path)
        })

    return {
        "run_id": run_id,
        "run_dir": run_dir_rel,
        "git_initialized": git_initialized,
        "agent_workspaces": agent_workspaces
    }


def create_agent_prompt(original_prompt: str, agent_workspace: Dict[str, Any]) -> str:
    """
    Create an enhanced prompt for an agent with git commit instructions.

    Args:
        original_prompt: The original user prompt
        agent_workspace: Workspace info for this agent

    Returns:
        Enhanced prompt with system instructions
    """
    agent_id = agent_workspace["agent_id"]
    branch_name = agent_workspace["branch_name"]

    system_instructions = f"""
## IMPORTANT: Workspace and Git Instructions

You are Agent {agent_id} working on branch `{branch_name}`.

**Your working directory is: /workspace**

All files you create should be placed in /workspace.

**CRITICAL: At the end of your work, you MUST commit all your changes:**

1. Stage all your changes:
   ```bash
   git add -A
   ```

2. Commit with a descriptive message:
   ```bash
   git commit -m "Agent {agent_id}: <brief description of what you implemented>"
   ```

Make sure to commit ALL files you created or modified before finishing.

---

## Your Task:

{original_prompt}
"""

    return system_instructions


def get_mcp_options_for_agent(agent_workspace: Dict[str, Any]) -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions with MCP server configuration for a specific agent.

    Args:
        agent_workspace: Workspace configuration for this agent

    Returns:
        ClaudeAgentOptions configured for the agent's worktree
    """
    docker_path = agent_workspace["docker_path"]

    return ClaudeAgentOptions(
        mcp_servers={
            "claude-code-docker": {
                "type": "stdio",
                "command": "docker",
                "args": [
                    "run", "-i", "--rm",
                    "-v", f"{docker_path}:/workspace",
                    DOCKER_MCP_IMAGE,
                    "claude", "mcp", "serve"
                ],
                "env": {
                    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY
                }
            }
        },
        allowed_tools=["mcp__claude-code-docker__*"]
    )


def get_mcp_options() -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions with MCP server configuration (legacy, uses root workspace).
    """
    return ClaudeAgentOptions(
        mcp_servers={
            "claude-code-docker": {
                "type": "stdio",
                "command": "docker",
                "args": [
                    "run", "-i", "--rm",
                    "-v", f"{WORKSPACE_PATH}:/workspace",
                    DOCKER_MCP_IMAGE,
                    "claude", "mcp", "serve"
                ],
                "env": {
                    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY
                }
            }
        },
        allowed_tools=["mcp__claude-code-docker__*"]
    )


async def run_agent(agent_id: int, prompt: str, agent_workspace: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run a single Claude agent with the given prompt.

    Args:
        agent_id: Identifier for this agent instance
        prompt: The prompt to send to the agent
        agent_workspace: Optional workspace configuration for git workflow

    Returns:
        Dictionary with agent results
    """
    logger.info(f"Agent {agent_id}: Starting with prompt: {prompt[:50]}...")

    result = {
        "agent_id": agent_id,
        "status": "pending",
        "output": "",
        "messages": []
    }

    # Add workspace info to result if available
    if agent_workspace:
        result["workspace"] = {
            "worktree_path": agent_workspace.get("worktree_path"),
            "branch_name": agent_workspace.get("branch_name")
        }

    # Pre-flight check: verify Docker is available
    docker_check = check_docker_available()
    if not docker_check["docker_running"]:
        result["status"] = "error"
        result["error"] = "Docker is not available or not running"
        result["docker_diagnostics"] = docker_check
        logger.error(f"Agent {agent_id}: Docker not available - {docker_check['errors']}")
        return result

    if not docker_check["mcp_image_exists"]:
        result["status"] = "error"
        result["error"] = f"MCP image '{DOCKER_MCP_IMAGE}' not found. Please build it first."
        result["docker_diagnostics"] = docker_check
        logger.error(f"Agent {agent_id}: MCP image not found")
        return result

    try:
        # Use agent-specific workspace if provided, otherwise use default
        if agent_workspace:
            options = get_mcp_options_for_agent(agent_workspace)
            workspace_path = agent_workspace["docker_path"]
        else:
            options = get_mcp_options()
            workspace_path = WORKSPACE_PATH
        logger.info(f"Agent {agent_id}: MCP options configured - image: {DOCKER_MCP_IMAGE}, workspace: {workspace_path}")

        async for message in query(prompt=prompt, options=options):
            # Log message type for debugging
            message_type = type(message).__name__
            logger.debug(f"Agent {agent_id}: Received message type: {message_type}")
            logger.debug(f"Agent {agent_id}: Message content: {str(message)[:200]}")

            if isinstance(message, ResultMessage):
                if message.subtype == "success":
                    result["status"] = "success"
                    result["output"] = message.result
                    logger.info(f"Agent {agent_id}: Completed successfully")
                elif message.subtype == "error":
                    result["status"] = "error"
                    result["error"] = message.result
                    # Log API errors with full details for investigation
                    error_details = {
                        "agent_id": agent_id,
                        "error_message": message.result,
                        "timestamp": datetime.now().isoformat(),
                        "workspace": workspace_path
                    }
                    logger.error(f"Agent {agent_id}: API/SDK Error - {message.result}")
                    logger.error(f"Agent {agent_id}: Error details: {json.dumps(error_details)}")
            else:
                # Capture other message types
                result["messages"].append(str(message))
                logger.debug(f"Agent {agent_id}: Other message - {str(message)[:100]}")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        logger.error(f"Agent {agent_id}: Exception - {e}")
        logger.error(f"Agent {agent_id}: Traceback:\n{traceback.format_exc()}")

    return result


async def orchestrate_agents(prompt: str, agent_count: int) -> Dict[str, Any]:
    """
    Orchestrate multiple agents to work on the same prompt concurrently.

    Sets up a git repository with worktrees for each agent and adds
    commit instructions to their prompts.

    Args:
        prompt: The prompt to send to all agents
        agent_count: Number of agents to spawn

    Returns:
        Dictionary with run info and results from all agents
    """
    logger.info(f"Orchestrating {agent_count} agents for prompt: {prompt[:50]}...")

    # Set up the run environment with git repo and worktrees
    run_env = setup_run_environment(agent_count)
    logger.info(f"Created run environment: {run_env['run_id']} with {len(run_env['agent_workspaces'])} worktrees")

    # Create tasks for all agents with their specific workspaces and enhanced prompts
    tasks = []
    for agent_ws in run_env["agent_workspaces"]:
        agent_id = agent_ws["agent_id"]
        # Create enhanced prompt with git commit instructions
        enhanced_prompt = create_agent_prompt(prompt, agent_ws)
        tasks.append(run_agent(agent_id, enhanced_prompt, agent_ws))

    # Run all agents concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            agent_ws = run_env["agent_workspaces"][i]
            processed_results.append({
                "agent_id": agent_ws["agent_id"],
                "status": "error",
                "error": str(result),
                "workspace": {
                    "worktree_path": agent_ws["worktree_path"],
                    "branch_name": agent_ws["branch_name"]
                }
            })
        else:
            processed_results.append(result)

    return {
        "run_info": {
            "run_id": run_env["run_id"],
            "run_dir": run_env["run_dir"],
            "git_initialized": run_env["git_initialized"]
        },
        "results": processed_results
    }


@app.route("/orchestrate", methods=["POST"])
def orchestrate():
    """
    Handle orchestration requests from the frontend.
    Expects JSON body with 'prompt' and 'agent_count'.

    Creates a git repository for the run with a worktree per agent.
    Each agent gets instructions to commit their changes to their branch.
    """
    try:
        data = request.get_json()
        prompt = data.get("prompt", "").strip()
        agent_count = data.get("agent_count", 1)

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        if not isinstance(agent_count, int) or agent_count < 1 or agent_count > 10:
            return jsonify({"error": "Agent count must be between 1 and 10"}), 400

        if not ANTHROPIC_API_KEY:
            return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

        logger.info(f"Received orchestration request: {agent_count} agents")

        # Run the async orchestration
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            orchestration_result = loop.run_until_complete(
                orchestrate_agents(prompt, agent_count)
            )
        finally:
            loop.close()

        # Extract results from the orchestration
        results = orchestration_result["results"]
        run_info = orchestration_result["run_info"]

        # Count successes and failures
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")

        return jsonify({
            "status": "completed",
            "run_info": run_info,
            "summary": {
                "total_agents": agent_count,
                "successful": success_count,
                "failed": error_count
            },
            "results": results
        })

    except Exception as e:
        logger.error(f"Orchestration error: {e}")
        logger.error(f"Orchestration traceback:\n{traceback.format_exc()}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/health")
def health():
    """Health check endpoint for Kubernetes probes."""
    return jsonify({"status": "healthy"})


@app.route("/ready")
def ready():
    """Readiness check endpoint for Kubernetes probes."""
    # Check if API key is configured
    if not ANTHROPIC_API_KEY:
        return jsonify({"status": "not_ready", "reason": "ANTHROPIC_API_KEY not set"}), 503
    return jsonify({"status": "ready"})


@app.route("/diagnostics")
def diagnostics():
    """
    Diagnostic endpoint to check Docker and system status.
    Use this to troubleshoot issues with agent execution.
    """
    # List workspace files for debugging
    workspace_files = []
    try:
        if os.path.exists(WORKSPACE_LOCAL):
            workspace_files = os.listdir(WORKSPACE_LOCAL)[:20]  # Limit to 20 files
    except Exception as e:
        workspace_files = [f"Error listing: {e}"]

    diag = {
        "timestamp": datetime.now().isoformat(),
        "environment": {
            "ANTHROPIC_API_KEY": "***SET***" if ANTHROPIC_API_KEY else "NOT SET",
            "WORKSPACE_PATH": WORKSPACE_PATH,  # Path used for docker run -v (on Docker host)
            "WORKSPACE_LOCAL": WORKSPACE_LOCAL,  # Path inside this container
            "DOCKER_MCP_IMAGE": DOCKER_MCP_IMAGE,
            "LOG_DIR": LOG_DIR,
            "LOG_LEVEL": LOG_LEVEL,
            "POD_NAME": os.getenv("POD_NAME", "unknown"),
        },
        "docker": check_docker_available(),
        "filesystem": {
            "workspace_local_exists": os.path.exists(WORKSPACE_LOCAL),
            "workspace_local_writable": os.access(WORKSPACE_LOCAL, os.W_OK) if os.path.exists(WORKSPACE_LOCAL) else False,
            "workspace_files": workspace_files,
            "log_dir_exists": os.path.exists(LOG_DIR),
            "log_dir_writable": os.access(LOG_DIR, os.W_OK) if os.path.exists(LOG_DIR) else False,
        }
    }

    logger.info(f"Diagnostics requested: {json.dumps(diag, indent=2)}")

    # Determine overall status
    docker_ok = (
        diag["docker"]["docker_cli"] and
        diag["docker"]["docker_socket"] and
        diag["docker"]["docker_running"] and
        diag["docker"]["mcp_image_exists"]
    )

    diag["status"] = "ok" if docker_ok else "issues_detected"

    return jsonify(diag)


@app.route("/test-docker")
def test_docker():
    """
    Test Docker by running a simple command.
    """
    result = {
        "test": "docker_hello_world",
        "success": False,
        "output": "",
        "error": ""
    }

    try:
        proc = subprocess.run(
            ["docker", "run", "--rm", "alpine:latest", "echo", "Hello from Docker!"],
            capture_output=True,
            text=True,
            timeout=60
        )
        result["success"] = proc.returncode == 0
        result["output"] = proc.stdout.strip()
        result["error"] = proc.stderr.strip() if proc.returncode != 0 else ""
        result["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        result["error"] = "Command timed out after 60 seconds"
    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    logger.info(f"Docker test result: {json.dumps(result, indent=2)}")

    return jsonify(result)


@app.route("/workspace")
def list_workspace():
    """
    List files in the workspace directory.
    Use this to see files created by MCP agents.
    """
    result = {
        "workspace_path": WORKSPACE_LOCAL,
        "docker_workspace_path": WORKSPACE_PATH,
        "files": [],
        "error": None
    }

    try:
        if not os.path.exists(WORKSPACE_LOCAL):
            result["error"] = f"Workspace directory does not exist: {WORKSPACE_LOCAL}"
            return jsonify(result), 404

        # Walk through workspace and list files
        for root, dirs, files in os.walk(WORKSPACE_LOCAL):
            rel_root = os.path.relpath(root, WORKSPACE_LOCAL)
            if rel_root == ".":
                rel_root = ""

            for f in files:
                file_path = os.path.join(rel_root, f) if rel_root else f
                full_path = os.path.join(root, f)
                try:
                    stat = os.stat(full_path)
                    result["files"].append({
                        "path": file_path,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    result["files"].append({
                        "path": file_path,
                        "error": str(e)
                    })

            # Limit depth and total files
            if len(result["files"]) > 100:
                result["truncated"] = True
                break

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error listing workspace: {e}")
        return jsonify(result), 500

    return jsonify(result)


@app.route("/workspace/<path:filepath>")
def get_workspace_file(filepath):
    """
    Get contents of a specific file from the workspace.
    """
    full_path = os.path.join(WORKSPACE_LOCAL, filepath)

    # Security: ensure path is within workspace
    if not os.path.abspath(full_path).startswith(os.path.abspath(WORKSPACE_LOCAL)):
        return jsonify({"error": "Access denied: path traversal detected"}), 403

    if not os.path.exists(full_path):
        return jsonify({"error": f"File not found: {filepath}"}), 404

    if os.path.isdir(full_path):
        return jsonify({"error": f"Path is a directory: {filepath}"}), 400

    try:
        # Limit file size to 1MB for safety
        if os.path.getsize(full_path) > 1024 * 1024:
            return jsonify({"error": "File too large (>1MB)"}), 413

        with open(full_path, 'r') as f:
            content = f.read()

        return jsonify({
            "path": filepath,
            "content": content,
            "size": len(content)
        })
    except UnicodeDecodeError:
        return jsonify({"error": "Binary file, cannot display as text"}), 415
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
