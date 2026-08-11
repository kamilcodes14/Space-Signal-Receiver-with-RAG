"""
Flask blueprint for the RAG chat widget.

Wire it into the existing app (app_web.py or app.py) with:

    from rag_api.chat import chat_bp
    app.register_blueprint(chat_bp)

Requires ANTHROPIC_API_KEY set in the environment before the agent
is first used (lazy-loaded so importing this file doesn't require
the index to exist yet).
"""

from flask import Blueprint, jsonify, request

from rag.agent import RAGAgent

chat_bp = Blueprint("chat", __name__)

_agent = None


def get_agent() -> RAGAgent:
    global _agent
    if _agent is None:
        _agent = RAGAgent()
    return _agent


@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    try:
        agent = get_agent()
        result = agent.ask(message)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"agent failed: {exc}"}), 500

    return jsonify(result)
