"""
Frontend web application for Claude Multi-Agent MCP System.
Allows users to enter prompts and specify the number of agents to work on them.
"""

import os
import logging
from flask import Flask, render_template, request, jsonify
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Backend orchestrator service URL (Kubernetes service DNS)
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator-service.backend.svc.cluster.local:8080")


@app.route("/")
def index():
    """Render the main page with prompt input form."""
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit_task():
    """
    Handle form submission - send prompt and agent count to orchestrator.
    """
    try:
        data = request.get_json()
        prompt = data.get("prompt", "").strip()
        agent_count = data.get("agent_count", 1)

        if not prompt:
            return jsonify({"error": "Prompt cannot be empty"}), 400

        if not isinstance(agent_count, int) or agent_count < 1 or agent_count > 10:
            return jsonify({"error": "Agent count must be between 1 and 10"}), 400

        logger.info(f"Submitting task with {agent_count} agents: {prompt[:50]}...")

        # Call the orchestrator service
        response = requests.post(
            f"{ORCHESTRATOR_URL}/orchestrate",
            json={
                "prompt": prompt,
                "agent_count": agent_count
            },
            timeout=300  # 5 minute timeout for long-running tasks
        )

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            logger.error(f"Orchestrator error: {response.status_code} - {response.text}")
            return jsonify({"error": f"Orchestrator error: {response.text}"}), response.status_code

    except requests.exceptions.Timeout:
        logger.error("Request to orchestrator timed out")
        return jsonify({"error": "Request timed out. The task may still be processing."}), 504
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to orchestrator: {e}")
        return jsonify({"error": "Cannot connect to orchestrator service"}), 503
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint for Kubernetes probes."""
    return jsonify({"status": "healthy"})


@app.route("/ready")
def ready():
    """Readiness check endpoint for Kubernetes probes."""
    return jsonify({"status": "ready"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
