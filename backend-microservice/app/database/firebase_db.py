"""
Firebase Manager - Handles all Firebase Auth and Firestore database operations.
Replaces the previous SupabaseManager with equivalent functionality.
"""

import os
import logging
import traceback
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import firebase_admin
from firebase_admin import auth, credentials, firestore
from google.cloud.firestore_v1 import FieldFilter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FirebaseManager:
    """Handles all Firebase database and auth operations"""

    def __init__(self):
        self._initialize_firebase()
        self.db = firestore.client()

    def _initialize_firebase(self):
        """Initialize the Firebase Admin SDK (only once)."""
        if firebase_admin._apps:
            # Already initialized
            return

        service_account_path = os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_PATH", "./firebase-service-account.json"
        )

        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized with service account file")
        else:
            # Fall back to Application Default Credentials (e.g. Cloud Run, GCE)
            firebase_admin.initialize_app()
            logger.info("Firebase initialized with application default credentials")

    # ──────────────────────────────────────────────
    # Error handling
    # ──────────────────────────────────────────────

    def _handle_error(self, operation: str, error: Exception) -> Dict[str, Any]:
        """Centralized error handling"""
        error_msg = str(error)
        logger.error(f"Error in {operation}: {error_msg}")

        if "ALREADY_EXISTS" in error_msg:
            return {"success": False, "error": "Record already exists."}
        elif "NOT_FOUND" in error_msg:
            return {"success": False, "error": "Record not found."}
        elif "PERMISSION_DENIED" in error_msg:
            return {"success": False, "error": "Permission denied."}
        elif "UNAUTHENTICATED" in error_msg:
            return {
                "success": False,
                "error": "Authentication expired. Please sign in again.",
            }
        else:
            return {"success": False, "error": f"Database error: {error_msg}"}

    # ──────────────────────────────────────────────
    # Authentication
    # ──────────────────────────────────────────────

    def sign_up(
        self, email: str, password: str, full_name: str = ""
    ) -> Dict[str, Any]:
        """Create a new Firebase Auth user and a Firestore profile."""
        try:
            user_record = auth.create_user(
                email=email,
                password=password,
                display_name=full_name or email.split("@")[0],
            )

            # Create a profile document in Firestore
            self.db.collection("profiles").document(user_record.uid).set(
                {
                    "email": email,
                    "full_name": full_name,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )

            # Create default user settings
            self.db.collection("user_settings").document(user_record.uid).set(
                {
                    "user_id": user_record.uid,
                    "max_questions": 5,
                    "model_name": "gpt-4.1-nano-2025-04-14",
                    "temperature": 0.3,
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                    "api_provider": "openai",
                    "user_api_key": "",
                    "base_url": "",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )

            # Generate a custom token so the client can sign in immediately
            custom_token = auth.create_custom_token(user_record.uid).decode("utf-8")

            return {
                "success": True,
                "user": {
                    "uid": user_record.uid,
                    "email": user_record.email,
                    "display_name": user_record.display_name,
                },
                "custom_token": custom_token,
            }
        except auth.EmailAlreadyExistsError:
            return {"success": False, "error": "Email already registered."}
        except Exception as e:
            return self._handle_error("sign_up", e)

    def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in with email/password using Firebase REST Identity Toolkit API.

        Returns an ID token that the client can use as a Bearer token.
        """
        import requests as _requests

        api_key = os.getenv("FIREBASE_API_KEY", "")
        if not api_key:
            return {"success": False, "error": "FIREBASE_API_KEY not configured"}

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        }
        try:
            resp = _requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if resp.status_code != 200:
                error_message = data.get("error", {}).get("message", "Login failed")
                return {"success": False, "error": error_message}

            id_token = data.get("idToken", "")
            refresh_token = data.get("refreshToken", "")
            local_id = data.get("localId", "")
            expires_in = data.get("expiresIn", "3600")

            return {
                "success": True,
                "user": {
                    "uid": local_id,
                    "email": email,
                    "display_name": data.get("displayName", ""),
                },
                "session": {
                    "access_token": id_token,
                    "refresh_token": refresh_token,
                    "expires_in": int(expires_in),
                },
            }
        except Exception as e:
            return self._handle_error("sign_in", e)

    def exchange_custom_token(self, custom_token: str) -> Optional[str]:
        """Exchange a custom token for a Firebase ID token via REST API."""
        import requests as _requests

        api_key = os.getenv("FIREBASE_API_KEY", "")
        if not api_key:
            logger.error("FIREBASE_API_KEY not configured")
            return None

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}"
        payload = {"token": custom_token, "returnSecureToken": True}
        try:
            resp = _requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200:
                return data.get("idToken")
            logger.error(f"Failed to exchange custom token: {data}")
            return None
        except Exception as e:
            logger.error(f"Error exchanging custom token: {e}")
            return None

    def verify_id_token(self, id_token: str) -> Optional[Dict[str, Any]]:
        """Verify a Firebase ID token and return decoded claims."""
        try:
            decoded = auth.verify_id_token(id_token, clock_skew_seconds=10)
            return decoded
        except auth.ExpiredIdTokenError:
            logger.warning("Firebase ID token has expired")
            return None
        except auth.InvalidIdTokenError as e:
            logger.warning(f"Invalid Firebase ID token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error verifying ID token: {e}")
            return None

    def get_user_by_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get Firebase Auth user record by UID."""
        try:
            user_record = auth.get_user(uid)
            return {
                "uid": user_record.uid,
                "email": user_record.email,
                "display_name": user_record.display_name,
            }
        except Exception as e:
            logger.error(f"Error getting user by UID: {e}")
            return None

    # ──────────────────────────────────────────────
    # User Profile
    # ──────────────────────────────────────────────

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile from Firestore."""
        try:
            doc = self.db.collection("profiles").document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching user profile: {e}")
            return None

    def update_user_profile(
        self, user_id: str, profile_data: Dict[str, Any]
    ) -> bool:
        """Update user profile in Firestore."""
        try:
            profile_data["updated_at"] = datetime.now().isoformat()
            self.db.collection("profiles").document(user_id).update(profile_data)
            return True
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            return False

    # ──────────────────────────────────────────────
    # User Settings
    # ──────────────────────────────────────────────

    def get_user_settings(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user settings from Firestore."""
        try:
            doc = self.db.collection("user_settings").document(user_id).get()
            if doc.exists:
                return doc.to_dict()
            else:
                # Create default settings
                default_settings = {
                    "user_id": user_id,
                    "max_questions": 5,
                    "model_name": "gpt-4.1-nano-2025-04-14",
                    "temperature": 0.3,
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                    "api_provider": "openai",
                    "user_api_key": "",
                    "base_url": "",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                self.db.collection("user_settings").document(user_id).set(
                    default_settings
                )
                return default_settings
        except Exception as e:
            logger.error(f"Error fetching user settings: {e}")
            return {
                "max_questions": 5,
                "model_name": "gpt-4.1-nano-2025-04-14",
                "temperature": 0.3,
                "chunk_size": 500,
                "chunk_overlap": 50,
                "api_provider": "openai",
                "user_api_key": "",
                "base_url": "",
            }

    def update_user_settings(
        self, user_id: str, settings: Dict[str, Any]
    ) -> bool:
        """Update user settings in Firestore."""
        try:
            settings["updated_at"] = datetime.now().isoformat()
            doc_ref = self.db.collection("user_settings").document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                doc_ref.update(settings)
            else:
                settings["user_id"] = user_id
                settings["created_at"] = datetime.now().isoformat()
                doc_ref.set(settings)
            return True
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return False

    # ──────────────────────────────────────────────
    # Interview Sessions
    # ──────────────────────────────────────────────

    def create_interview_session(
        self, user_id: str, session_data: Dict[str, Any], session_id: str = None
    ) -> Optional[str]:
        """Create a new interview session in Firestore."""
        logger.info(f"Creating interview session for user: {user_id}")

        try:
            safe_data = {
                "user_id": user_id,
                "title": session_data.get(
                    "title",
                    f"Interview Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                ),
                "status": session_data.get("status", "in_progress"),
                "interview_plan": session_data.get("interview_plan", []),
                "current_question_idx": session_data.get("current_question_idx", 0),
                "interview_notes": session_data.get("interview_notes", []),
                "conversation_history": session_data.get(
                    "conversation_history", []
                ),
                "resume_content": session_data.get("resume_content", ""),
                "job_description": session_data.get("job_description", ""),
                "total_questions": session_data.get("total_questions", 0),
                "average_score": session_data.get("average_score"),
                "final_report": session_data.get("final_report", ""),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            if session_id:
                # Use the provided session_id as the document ID
                self.db.collection("interview_sessions").document(
                    session_id
                ).set(safe_data)
                logger.info(f"Session created with ID: {session_id}")
                return session_id
            else:
                # Auto-generate ID
                _, doc_ref = self.db.collection("interview_sessions").add(
                    safe_data
                )
                logger.info(f"Session created with ID: {doc_ref.id}")
                return doc_ref.id

        except Exception as e:
            logger.error(f"Error creating interview session: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")

            # Fallback: minimal save
            try:
                logger.info("Attempting minimal session save...")
                minimal_data = {
                    "user_id": user_id,
                    "status": "in_progress",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                if session_id:
                    self.db.collection("interview_sessions").document(
                        session_id
                    ).set(minimal_data)
                    return session_id
                else:
                    _, doc_ref = self.db.collection("interview_sessions").add(
                        minimal_data
                    )
                    return doc_ref.id
            except Exception as minimal_error:
                logger.error(f"Minimal session save failed: {minimal_error}")
                return None

    def update_interview_session(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        user_id: str = None,
    ) -> bool:
        """Update an existing interview session in Firestore."""
        try:
            safe_data = {"updated_at": datetime.now().isoformat()}

            allowed_fields = [
                "status",
                "interview_plan",
                "current_question_idx",
                "interview_notes",
                "conversation_history",
                "resume_content",
                "job_description",
                "total_questions",
                "average_score",
                "final_report",
                "title",
            ]

            for field in allowed_fields:
                if field in session_data:
                    safe_data[field] = session_data[field]

            doc_ref = self.db.collection("interview_sessions").document(
                session_id
            )
            doc = doc_ref.get()

            if doc.exists:
                doc_ref.update(safe_data)
                logger.info(f"Session {session_id} updated successfully.")
                return True
            else:
                logger.warning(
                    f"Session {session_id} not found. Attempting to recreate..."
                )
                fallback_user_id = user_id or session_data.get("user_id")
                if not fallback_user_id:
                    logger.error("Cannot recreate session without user_id")
                    return False

                recreate_data = {
                    "user_id": fallback_user_id,
                    "status": session_data.get("status", "in_progress"),
                    "title": session_data.get(
                        "title",
                        f"Recovered Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    ),
                    "total_questions": session_data.get("total_questions", 0),
                    "current_question_idx": session_data.get(
                        "current_question_idx", 0
                    ),
                    "interview_plan": session_data.get("interview_plan", []),
                    "interview_notes": session_data.get("interview_notes", []),
                    "conversation_history": session_data.get(
                        "conversation_history", []
                    ),
                    "resume_content": session_data.get("resume_content", ""),
                    "job_description": session_data.get("job_description", ""),
                    "final_report": session_data.get("final_report", ""),
                    "average_score": session_data.get("average_score"),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                doc_ref.set(recreate_data)
                logger.info(f"Session {session_id} recreated successfully.")
                return True

        except Exception as e:
            logger.error(f"Error updating interview session: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    def get_interview_session(
        self, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get interview session by ID."""
        try:
            doc = (
                self.db.collection("interview_sessions")
                .document(session_id)
                .get()
            )
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching interview session: {e}")
            return None

    def get_user_interview_sessions(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all interview sessions for a user."""
        logger.info(
            f"Fetching interview sessions for user: {user_id}, limit: {limit}"
        )

        try:
            query = (
                self.db.collection("interview_sessions")
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = query.stream()

            sessions = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                sessions.append(data)

            logger.info(f"Found {len(sessions)} sessions for user {user_id}")
            return sessions

        except Exception as e:
            logger.error(f"Error fetching user interview sessions: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    def delete_interview_session(self, session_id: str) -> bool:
        """Delete an interview session."""
        try:
            self.db.collection("interview_sessions").document(
                session_id
            ).delete()
            return True
        except Exception as e:
            logger.error(f"Error deleting interview session: {e}")
            return False

    # ──────────────────────────────────────────────
    # Interview Reports
    # ──────────────────────────────────────────────

    def save_interview_report(
        self,
        user_id: str,
        session_id: Optional[str],
        report_data: Dict[str, Any],
    ) -> Optional[str]:
        """Save or update an interview report in Firestore."""
        logger.info(
            f"Saving interview report for user: {user_id}, session: {session_id}"
        )

        try:
            # Validate session exists
            if session_id:
                session_exists = self.get_interview_session(session_id)
                if not session_exists:
                    logger.error(
                        f"Session ID {session_id} does not exist. Aborting report save."
                    )
                    return None

            report_content = report_data.get("report_content", "")
            if not report_content:
                logger.error("Attempted to save report with empty content.")
                return None

            safe_report = {
                "user_id": user_id,
                "session_id": session_id,
                "title": report_data.get(
                    "title",
                    f"Interview Report {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                ),
                "report_content": report_content,
                "summary": report_data.get("summary", {}),
                "scores": report_data.get("scores", {}),
                "recommendations": report_data.get("recommendations", ""),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            # Check if a report already exists for this user+session
            if session_id:
                existing_query = (
                    self.db.collection("interview_reports")
                    .where(filter=FieldFilter("user_id", "==", user_id))
                    .where(
                        filter=FieldFilter("session_id", "==", session_id)
                    )
                    .limit(1)
                )
                existing_docs = list(existing_query.stream())

                if existing_docs:
                    # Update existing
                    report_id = existing_docs[0].id
                    self.db.collection("interview_reports").document(
                        report_id
                    ).update(safe_report)
                    logger.info(f"Report updated with ID: {report_id}")
                    return report_id

            # Insert new report
            _, doc_ref = self.db.collection("interview_reports").add(
                safe_report
            )
            logger.info(f"Report created with ID: {doc_ref.id}")
            return doc_ref.id

        except Exception as e:
            logger.error(f"Exception in save_interview_report: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return None

    def get_user_reports(
        self, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all reports for a user."""
        logger.info(f"Fetching reports for user: {user_id}, limit: {limit}")

        try:
            query = (
                self.db.collection("interview_reports")
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = query.stream()

            reports = []
            for doc in docs:
                data = doc.to_dict()
                # Only return summary fields for list view
                reports.append(
                    {
                        "id": doc.id,
                        "title": data.get("title", ""),
                        "created_at": data.get("created_at", ""),
                    }
                )

            logger.info(f"Found {len(reports)} reports for user {user_id}")
            return reports

        except Exception as e:
            logger.error(f"Error fetching user reports: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report by ID."""
        try:
            doc = (
                self.db.collection("interview_reports")
                .document(report_id)
                .get()
            )
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching report: {e}")
            return None

    def delete_report(self, report_id: str) -> bool:
        """Delete a report."""
        try:
            self.db.collection("interview_reports").document(
                report_id
            ).delete()
            return True
        except Exception as e:
            logger.error(f"Error deleting report: {e}")
            return False

    # ──────────────────────────────────────────────
    # Dashboard Statistics
    # ──────────────────────────────────────────────

    def get_user_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard statistics for a user."""
        try:
            query = (
                self.db.collection("interview_sessions")
                .where(filter=FieldFilter("user_id", "==", user_id))
            )
            docs = query.stream()

            sessions = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                sessions.append(data)

            total_sessions = len(sessions)
            completed_sessions = len(
                [s for s in sessions if s.get("status") == "completed"]
            )

            if completed_sessions > 0:
                avg_scores = [
                    s.get("average_score", 0)
                    for s in sessions
                    if s.get("average_score") is not None
                ]
                overall_avg_score = (
                    sum(avg_scores) / len(avg_scores) if avg_scores else 0
                )
                total_questions_answered = sum(
                    [
                        s.get("total_questions", 0)
                        for s in sessions
                        if s.get("total_questions")
                    ]
                )
            else:
                overall_avg_score = 0
                total_questions_answered = 0

            # Recent activity (last 30 days)
            thirty_days_ago = (
                datetime.now() - timedelta(days=30)
            ).isoformat()
            recent_sessions = [
                s
                for s in sessions
                if s.get("created_at", "") >= thirty_days_ago
            ]

            return {
                "total_sessions": total_sessions,
                "completed_sessions": completed_sessions,
                "in_progress_sessions": len(
                    [
                        s
                        for s in sessions
                        if s.get("status") == "in_progress"
                    ]
                ),
                "overall_avg_score": (
                    round(overall_avg_score, 1) if overall_avg_score else 0
                ),
                "total_questions_answered": total_questions_answered,
                "recent_activity": len(recent_sessions),
                "sessions": sessions[:10],
            }

        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return {
                "total_sessions": 0,
                "completed_sessions": 0,
                "in_progress_sessions": 0,
                "overall_avg_score": 0,
                "total_questions_answered": 0,
                "recent_activity": 0,
                "sessions": [],
            }

    # ──────────────────────────────────────────────
    # Profile – extended (Google sign-in / resume)
    # ──────────────────────────────────────────────

    def get_or_create_user_profile(
        self, uid: str, email: str, display_name: str = ""
    ) -> Dict[str, Any]:
        """Get existing profile or create one (used for Google sign-in)."""
        try:
            doc = self.db.collection("profiles").document(uid).get()
            is_new = not doc.exists
            if is_new:
                profile_data = {
                    "email": email,
                    "full_name": display_name or email.split("@")[0],
                    "profile_complete": False,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
                self.db.collection("profiles").document(uid).set(profile_data)
                self.db.collection("user_settings").document(uid).set({
                    "user_id": uid,
                    "max_questions": 5,
                    "model_name": "gpt-4.1-nano-2025-04-14",
                    "temperature": 0.3,
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                    "api_provider": "openai",
                    "user_api_key": "",
                    "base_url": "",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                })
                return {"data": {**profile_data, "id": uid}, "is_new": True}
            else:
                data = doc.to_dict()
                data["id"] = doc.id
                return {"data": data, "is_new": False}
        except Exception as e:
            logger.error(f"Error in get_or_create_user_profile: {e}")
            return {"data": {"id": uid, "email": email, "full_name": display_name}, "is_new": False}

    def update_user_profile_full(
        self, user_id: str, profile_data: Dict[str, Any]
    ) -> bool:
        """Update profile with merge (any fields)."""
        try:
            profile_data["updated_at"] = datetime.now().isoformat()
            self.db.collection("profiles").document(user_id).set(
                profile_data, merge=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating full profile: {e}")
            return False

    def store_resume_data(
        self, user_id: str, resume_text: str, filename: str, analysis_id: str, analysis: dict
    ) -> bool:
        """Store a lightweight resume summary in the user's profile document."""
        try:
            parsed = analysis.get("parsed_sections", {})
            resume_summary = {
                "name": parsed.get("name", ""),
                "contact": parsed.get("contact", {}),
                "skills": parsed.get("skills", [])[:10],
            }
            self.db.collection("profiles").document(user_id).set(
                {
                    "resume_filename": filename,
                    "current_analysis_id": analysis_id,
                    "resume_summary": resume_summary,
                    "resume_updated_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                },
                merge=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error storing resume data: {e}")
            return False

    def get_resume_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return resume analysis for a user, fetching from resume_analyses collection."""
        try:
            doc = self.db.collection("profiles").document(user_id).get()
            if not doc.exists:
                return None
            profile = doc.to_dict()
            analysis_id = profile.get("current_analysis_id")
            analysis = self.get_resume_analysis_by_id(analysis_id) if analysis_id else None

            if analysis and analysis_id:
                parsed_doc = self.db.collection("resume_parsed_sections").document(analysis_id).get()
                if parsed_doc.exists:
                    parsed_data = parsed_doc.to_dict()
                    analysis["parsed_sections"] = parsed_data.get("parsed_sections", {})

            return {
                "resume_filename": profile.get("resume_filename", ""),
                "resume_analysis": analysis,
                "resume_summary": profile.get("resume_summary", {}),
                "current_analysis_id": analysis_id,
                "resume_updated_at": profile.get("resume_updated_at"),
            }
        except Exception as e:
            logger.error(f"Error fetching resume data: {e}")
            return None

    # ──────────────────────────────────────────────
    # Resume Analyses
    # ──────────────────────────────────────────────

    def create_resume_analysis(self, user_id: str, analysis_id: str, filename: str) -> bool:
        """Create a new resume_analyses doc with status=processing."""
        try:
            self.db.collection("resume_analyses").document(analysis_id).set({
                "user_id": user_id,
                "analysis_id": analysis_id,
                "filename": filename,
                "status": "processing",
                "current_step": "parsing_document",
                "overall": {},
                "sections": [],
                "ats": {},
                "lackings": [],
                "quality_score": 0,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error creating resume analysis: {e}")
            return False

    def update_resume_analysis(self, analysis_id: str, data: dict) -> bool:
        """Update fields on an existing resume_analyses doc."""
        try:
            data["updated_at"] = datetime.now().isoformat()
            self.db.collection("resume_analyses").document(analysis_id).update(data)
            return True
        except Exception as e:
            logger.error(f"Error updating resume analysis {analysis_id}: {e}")
            return False

    def get_resume_analysis_by_id(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single resume_analyses doc by ID."""
        try:
            doc = self.db.collection("resume_analyses").document(analysis_id).get()
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching resume analysis {analysis_id}: {e}")
            return None

    def get_latest_resume_analysis(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the most recent resume_analyses doc for a user."""
        try:
            docs = (
                self.db.collection("resume_analyses")
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching latest resume analysis for {user_id}: {e}")
            return None

    def save_resume_parsed_sections(
        self, user_id: str, analysis_id: str, filename: str, parsed_sections: dict
    ) -> bool:
        """Create/overwrite resume_parsed_sections/{analysis_id}."""
        try:
            self.db.collection("resume_parsed_sections").document(analysis_id).set({
                "user_id": user_id,
                "analysis_id": analysis_id,
                "filename": filename,
                "parsed_sections": parsed_sections,
                "created_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error saving parsed sections for {analysis_id}: {e}")
            return False

    def save_token_usage(
        self, user_id: str, feature: str, analysis_id: str, usage: dict
    ) -> bool:
        """Add a doc to the token_usage admin collection."""
        try:
            self.db.collection("token_usage").add({
                "user_id": user_id,
                "feature": feature,
                "analysis_id": analysis_id,
                "usage": usage,
                "created_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error saving token usage for {analysis_id}: {e}")
            return False

    # ──────────────────────────────────────────────
    # Connection Test
    # ──────────────────────────────────────────────

    def test_connection(self) -> Dict[str, Any]:
        """Test database connection and schema."""
        try:
            collections_to_test = [
                "profiles",
                "user_settings",
                "interview_sessions",
                "interview_reports",
            ]
            accessible_collections = []

            for collection_name in collections_to_test:
                try:
                    # Try to read from the collection
                    self.db.collection(collection_name).limit(1).get()
                    accessible_collections.append(collection_name)
                except Exception:
                    pass

            return {
                "success": True,
                "accessible_collections": accessible_collections,
                "total_collections": len(accessible_collections),
            }

        except Exception as e:
            return self._handle_error("test_connection", e)
