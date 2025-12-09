from livekit.agents import cli, WorkerOptions

from src.routes.livekit.main import entrypoint


if __name__ == "__main__":
    """
    Dedicated entrypoint for the LiveKit voice agent worker.
    Run this in a separate process from the Flask dashboard.
    """
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="telephony_agent",
        )
    )


