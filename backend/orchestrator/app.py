"""
Backend Orchestrator for Claude Multi-Agent MCP System.
Receives prompts from frontend and spawns multiple Claude agents via MCP.
"""

import asyncio
import os
import json
import logging
from typing import List, Dict, Any
from flask import Flask, request, jsonify
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration from environment
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", "/workspace")
DOCKER_MCP_IMAGE = os.getenv("DOCKER_MCP_IMAGE", "claude-mcp:latest")


def get_mcp_options() -> ClaudeAgentOptions:
    """
    Create ClaudeAgentOptions with MCP server configuration.
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


async def run_agent(agent_id: int, prompt: str) -> Dict[str, Any]:
    """
    Run a single Claude agent with the given prompt.

    Args:
        agent_id: Identifier for this agent instance
        prompt: The prompt to send to the agent

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

    try:
        options = get_mcp_options()

        async for message in query(prompt=prompt, options=options):
            # Log message type for debugging
            message_type = type(message).__name__
            logger.debug(f"Agent {agent_id}: Received message type: {message_type}")

            if isinstance(message, ResultMessage):
                if message.subtype == "success":
                    result["status"] = "success"
                    result["output"] = message.result
                    logger.info(f"Agent {agent_id}: Completed successfully")
                elif message.subtype == "error":
                    result["status"] = "error"
                    result["error"] = message.result
                    logger.error(f"Agent {agent_id}: Error - {message.result}")
            else:
                # Capture other message types
                result["messages"].append(str(message))

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.error(f"Agent {agent_id}: Exception - {e}")

    return result


async def orchestrate_agents(prompt: str, agent_count: int) -> List[Dict[str, Any]]:
    """
    Orchestrate multiple agents to work on the same prompt concurrently.

    Args:
        prompt: The prompt to send to all agents
        agent_count: Number of agents to spawn

    Returns:
        List of results from all agents
    """
    logger.info(f"Orchestrating {agent_count} agents for prompt: {prompt[:50]}...")

    # Create tasks for all agents
    tasks = [
        run_agent(i + 1, prompt)
        for i in range(agent_count)
    ]

    # Run all agents concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "agent_id": i + 1,
                "status": "error",
                "error": str(result)
            })
        else:
            processed_results.append(result)

    return processed_results


@app.route("/orchestrate", methods=["POST"])
def orchestrate():
    """
    Handle orchestration requests from the frontend.
    Expects JSON body with 'prompt' and 'agent_count'.
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
            results = loop.run_until_complete(
                orchestrate_agents(prompt, agent_count)
            )
        finally:
            loop.close()

        # Count successes and failures
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")

        return jsonify({
            "status": "completed",
            "summary": {
                "total_agents": agent_count,
                "successful": success_count,
                "failed": error_count
            },
            "results": results
        })

    except Exception as e:
        logger.error(f"Orchestration error: {e}")
        return jsonify({"error": str(e)}), 500


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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
