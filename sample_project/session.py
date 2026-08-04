"""Session management without timeout."""


class SessionStore:
    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id):
        # VULNERABILITY: session has no expiry timestamp
        session_id = f"sess_{user_id}_{len(self.sessions)}"
        self.sessions[session_id] = {"user_id": user_id}
        return session_id

    def validate_session(self, session_id):
        # VULNERABILITY: no age check — sessions live forever
        return session_id in self.sessions
