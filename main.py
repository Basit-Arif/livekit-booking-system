from livekit.agents import cli, WorkerOptions

from src.app_factory import create_app
from src.routes.livekit.main import entrypoint


if __name__ == "__main__":
    # First, run LiveKit worker for voice agent
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="telephony_agent"
        )
    )

    # Optionally, start Flask app in parallel (for dashboard)
    # app = create_app()
    # app.run(host="0.0.0.0", port=5000, debug=True)
