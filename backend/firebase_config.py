import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

if not firebase_admin._apps:
    firebase_key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if firebase_key_json:
        try:
            cred_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("[STARTUP] Firebase initialized successfully via Environment Variable.")
        except Exception as e:
            print(f"[STARTUP] Failed to parse FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
            raise
    elif os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        print("[STARTUP] Firebase initialized successfully via local serviceAccountKey.json.")
    else:
        raise RuntimeError(
            "[STARTUP] Critical Error: No Firebase credentials found. "
            "Set FIREBASE_SERVICE_ACCOUNT_JSON env var or add serviceAccountKey.json."
        )

db = firestore.client()

# The Firebase project the frontend uses for auth. May differ from the service
# account project — tokens are verified via Google's public keys, not the SA key.
_FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "eduease-b955c")
_google_request = google_requests.Request()


def verify_firebase_token(id_token_str: str) -> dict:
    """Verify a Firebase ID token using Google's public signing keys.
    Works regardless of which project the service account key belongs to."""
    return google_id_token.verify_firebase_token(
        id_token_str, _google_request, audience=_FIREBASE_PROJECT_ID
    )
