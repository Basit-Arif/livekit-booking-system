from src.app_factory import create_app


if __name__ == "__main__":
    """
    Dedicated entrypoint for the Flask receptionist dashboard.
    Run the LiveKit worker from `livekit_worker.py` in a separate process.
    """
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)
