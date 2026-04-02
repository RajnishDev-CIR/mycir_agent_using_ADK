from google.adk.sessions import DatabaseSessionService
from mycir_agent.config import SESSION_DB_URL

# PostgreSQL-backed session service — persists state across turns and invocations.
# ADK's web UI and CLI runner pick this up automatically when the module is loaded.
# Make sure PostgreSQL is running: docker compose up -d
session_service = DatabaseSessionService(db_url=SESSION_DB_URL)
