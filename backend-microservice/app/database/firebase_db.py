"""
Firebase Manager - Handles all Firebase Auth and Firestore database operations.
Replaces the previous SupabaseManager with equivalent functionality.
"""

import os
import json
import copy
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
                reports.append(
                    {
                        "id": doc.id,
                        "session_id": data.get("session_id", ""),
                        "title": data.get("title", ""),
                        "created_at": data.get("created_at", ""),
                        "report_content": data.get("report_content", ""),
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
        """Update profile only for first-ever resume (sets active) or when this analysis is already active.

        New uploads do not replace the user's active resume; user sets active via set_active_resume.
        """
        try:
            parsed = analysis.get("parsed_sections", {})
            resume_summary = {
                "name": parsed.get("name", ""),
                "contact": parsed.get("contact", {}),
                "skills": parsed.get("skills", [])[:10],
            }
            prof_ref = self.db.collection("profiles").document(user_id)
            prof_snap = prof_ref.get()
            pdata = prof_snap.to_dict() if prof_snap.exists else {}
            active_id = pdata.get("current_analysis_id")

            update: Dict[str, Any] = {
                "resume_updated_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            if not active_id:
                update["current_analysis_id"] = analysis_id
                update["resume_filename"] = filename
                update["resume_summary"] = resume_summary
            elif active_id == analysis_id:
                update["resume_filename"] = filename
                update["resume_summary"] = resume_summary

            prof_ref.set(update, merge=True)
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
                    baseline = parsed_data.get("parsed_sections", {})
                    working = parsed_data.get("working_parsed_sections")
                    if working is None:
                        working = baseline
                    analysis["parsed_sections"] = working
                    analysis["original_parsed_sections"] = baseline

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

    def sweep_stale_resume_analyses(self, max_age_seconds: int) -> int:
        """Fail out resume_analyses docs stuck in `processing` past max_age_seconds.

        BackgroundTasks run in-process and are lost if the process restarts or is
        killed mid-analysis, leaving the Firestore doc `processing` forever with
        no error and no way for the client to recover. This is a defensive sweep
        run at startup (to clean up crash leftovers from a previous process) and
        periodically thereafter. Returns the number of docs marked failed.
        """
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        swept = 0
        try:
            query = self.db.collection("resume_analyses").where(
                filter=FieldFilter("status", "==", "processing")
            )
            for doc in query.stream():
                data = doc.to_dict()
                stamp = data.get("updated_at") or data.get("created_at")
                try:
                    ts = datetime.fromisoformat(stamp) if stamp else None
                except (TypeError, ValueError):
                    ts = None
                if ts is None or ts < cutoff:
                    doc.reference.update({
                        "status": "failed",
                        "current_step": "failed",
                        "error": "Analysis did not complete (server restarted or timed out).",
                        "updated_at": datetime.now().isoformat(),
                    })
                    swept += 1
        except Exception as e:
            logger.error(f"Error sweeping stale resume analyses: {e}")
        return swept

    def sweep_stale_dream_jobs(self, max_age_seconds: int) -> int:
        """Fail out dream_jobs docs stuck in a non-terminal status past max_age_seconds.

        Mirrors sweep_stale_resume_analyses — see that docstring for rationale.
        """
        cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
        swept = 0
        try:
            query = self.db.collection("dream_jobs").where(
                filter=FieldFilter("status", "in", ["pending", "normalizing", "analyzing"])
            )
            for doc in query.stream():
                data = doc.to_dict()
                stamp = data.get("updated_at") or data.get("created_at")
                try:
                    ts = datetime.fromisoformat(stamp) if stamp else None
                except (TypeError, ValueError):
                    ts = None
                if ts is None or ts < cutoff:
                    doc.reference.update({
                        "status": "failed",
                        "current_step": "failed",
                        "error": "Analysis did not complete (server restarted or timed out).",
                        "updated_at": datetime.now().isoformat(),
                    })
                    swept += 1
        except Exception as e:
            logger.error(f"Error sweeping stale dream jobs: {e}")
        return swept

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
        """Create/overwrite resume_parsed_sections/{analysis_id}.

        Baseline ``parsed_sections`` is immutable after first save; ``working_parsed_sections``
        is seeded to match and holds session edits (suggestions, manual PATCH).
        """
        try:
            baseline = copy.deepcopy(parsed_sections) if parsed_sections else {}
            self.db.collection("resume_parsed_sections").document(analysis_id).set({
                "user_id": user_id,
                "analysis_id": analysis_id,
                "filename": filename,
                "parsed_sections": baseline,
                "working_parsed_sections": copy.deepcopy(baseline),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error saving parsed sections for {analysis_id}: {e}")
            return False

    def get_resume_parsed_doc(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        try:
            doc = self.db.collection("resume_parsed_sections").document(analysis_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error reading resume_parsed_sections {analysis_id}: {e}")
            return None

    def ensure_working_parsed_sections(self, analysis_id: str) -> bool:
        """If working_parsed_sections is missing, copy from parsed_sections."""
        try:
            doc_ref = self.db.collection("resume_parsed_sections").document(analysis_id)
            snap = doc_ref.get()
            if not snap.exists:
                return False
            data = snap.to_dict()
            if data.get("working_parsed_sections") is not None:
                return True
            baseline = data.get("parsed_sections") or {}
            doc_ref.update({
                "working_parsed_sections": copy.deepcopy(baseline),
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"ensure_working_parsed_sections {analysis_id}: {e}")
            return False

    def set_working_parsed_sections(
        self, analysis_id: str, user_id: str, working: dict
    ) -> bool:
        """Replace working_parsed_sections after ownership check."""
        try:
            doc_ref = self.db.collection("resume_parsed_sections").document(analysis_id)
            snap = doc_ref.get()
            if not snap.exists:
                return False
            data = snap.to_dict()
            if data.get("user_id") != user_id:
                return False
            doc_ref.update({
                "working_parsed_sections": copy.deepcopy(working),
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"set_working_parsed_sections {analysis_id}: {e}")
            return False

    def merge_working_parsed_sections(
        self, analysis_id: str, user_id: str, patch: dict
    ) -> bool:
        """Deep-merge patch into working_parsed_sections."""
        try:
            doc_ref = self.db.collection("resume_parsed_sections").document(analysis_id)
            snap = doc_ref.get()
            if not snap.exists:
                return False
            data = snap.to_dict()
            if data.get("user_id") != user_id:
                return False
            self.ensure_working_parsed_sections(analysis_id)
            snap = doc_ref.get()
            data = snap.to_dict()
            working = copy.deepcopy(data.get("working_parsed_sections") or data.get("parsed_sections") or {})

            def _deep_merge(base: dict, upd: dict) -> dict:
                for k, v in upd.items():
                    if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                        _deep_merge(base[k], v)
                    else:
                        base[k] = copy.deepcopy(v)
                return base

            merged = _deep_merge(working, patch)
            doc_ref.update({
                "working_parsed_sections": merged,
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"merge_working_parsed_sections {analysis_id}: {e}")
            return False

    def working_parsed_differs_from_baseline(self, analysis_id: str) -> bool:
        try:
            data = self.get_resume_parsed_doc(analysis_id)
            if not data:
                return False
            a = data.get("parsed_sections") or {}
            b = data.get("working_parsed_sections")
            if b is None:
                return False
            return json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str)
        except Exception:
            return False

    def get_user_resume_analyses(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all resume analyses for a user, ordered by creation date descending."""
        try:
            docs = (
                self.db.collection("resume_analyses")
                .where(filter=FieldFilter("user_id", "==", user_id))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            results = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                results.append(data)
            return results
        except Exception as e:
            logger.error(f"Error fetching user resume analyses for {user_id}: {e}")
            return []

    def delete_resume_analysis(self, analysis_id: str, user_id: str) -> bool:
        """Delete a resume analysis and its parsed sections (with ownership check)."""
        try:
            doc = self.db.collection("resume_analyses").document(analysis_id).get()
            if not doc.exists:
                return False
            data = doc.to_dict()
            if data.get("user_id") != user_id:
                logger.warning(f"User {user_id} attempted to delete resume {analysis_id} owned by {data.get('user_id')}")
                return False
            # Delete parsed sections doc
            self.db.collection("resume_parsed_sections").document(analysis_id).delete()
            # Delete the analysis doc
            self.db.collection("resume_analyses").document(analysis_id).delete()
            # If this was the active resume, clear it from profile
            profile = self.db.collection("profiles").document(user_id).get()
            if profile.exists and profile.to_dict().get("current_analysis_id") == analysis_id:
                # Find the next most recent analysis to set as active
                analyses = self.get_user_resume_analyses(user_id, limit=2)
                next_active_id = None
                for a in analyses:
                    if a["id"] != analysis_id and a.get("status") == "completed":
                        next_active_id = a["id"]
                        break
                self.db.collection("profiles").document(user_id).update({
                    "current_analysis_id": next_active_id,
                    "updated_at": datetime.now().isoformat(),
                })
            return True
        except Exception as e:
            logger.error(f"Error deleting resume analysis {analysis_id}: {e}")
            return False

    def set_active_resume(self, user_id: str, analysis_id: str) -> bool:
        """Set a specific resume analysis as the active one for a user."""
        try:
            doc = self.db.collection("resume_analyses").document(analysis_id).get()
            if not doc.exists:
                return False
            data = doc.to_dict()
            if data.get("user_id") != user_id:
                return False
            self.db.collection("profiles").document(user_id).update({
                "current_analysis_id": analysis_id,
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error setting active resume {analysis_id} for {user_id}: {e}")
            return False

    # ──────────────────────────────────────────────
    # Dream Jobs
    # ──────────────────────────────────────────────

    def create_dream_job(
        self,
        uid: str,
        dream_job_id: str,
        company: str,
        role_title: str,
        jd_text: str,
        source: str,
        source_url: Optional[str],
        resume_analysis_id: str,
    ) -> bool:
        """Create a new dream_jobs doc with status=pending."""
        try:
            self.db.collection("dream_jobs").document(dream_job_id).set({
                "uid": uid,
                "dream_job_id": dream_job_id,
                "company": company,
                "role_title": role_title,
                "jd_text": jd_text,
                "jd_normalized": {},
                "source": source,
                "source_url": source_url,
                "resume_analysis_id": resume_analysis_id,
                "status": "pending",
                "current_step": "queued",
                "error": None,
                "result": {},
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })
            return True
        except Exception as e:
            logger.error(f"Error creating dream job {dream_job_id}: {e}")
            return False

    def update_dream_job(self, dream_job_id: str, data: dict) -> bool:
        """Update fields on an existing dream_jobs doc."""
        try:
            data["updated_at"] = datetime.now().isoformat()
            self.db.collection("dream_jobs").document(dream_job_id).update(data)
            return True
        except Exception as e:
            logger.error(f"Error updating dream job {dream_job_id}: {e}")
            return False

    def get_dream_job_by_id(self, dream_job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single dream_jobs doc by ID."""
        try:
            doc = self.db.collection("dream_jobs").document(dream_job_id).get()
            if doc.exists:
                data = doc.to_dict()
                data["id"] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Error fetching dream job {dream_job_id}: {e}")
            return None

    def list_user_dream_jobs(self, uid: str, limit: int = 50) -> list:
        """Return summary records for all dream jobs owned by uid."""
        try:
            docs = (
                self.db.collection("dream_jobs")
                .where(filter=FieldFilter("uid", "==", uid))
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            results = []
            for doc in docs:
                data = doc.to_dict()
                # Return summary fields only (omit heavy jd_text / result payload)
                results.append({
                    "id": doc.id,
                    "dream_job_id": data.get("dream_job_id"),
                    "company": data.get("company"),
                    "role_title": data.get("role_title"),
                    "source": data.get("source"),
                    "source_url": data.get("source_url"),
                    "resume_analysis_id": data.get("resume_analysis_id"),
                    "status": data.get("status"),
                    "current_step": data.get("current_step"),
                    "fit_score": (data.get("result") or {}).get("fit_score"),
                    "interview_chance": (data.get("result") or {}).get("interview_chance"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
            return results
        except Exception as e:
            logger.error(f"Error listing dream jobs for {uid}: {e}")
            return []

    def delete_dream_job(self, dream_job_id: str, uid: str) -> bool:
        """Delete a dream_jobs doc after verifying uid ownership."""
        try:
            doc = self.db.collection("dream_jobs").document(dream_job_id).get()
            if not doc.exists:
                return False
            data = doc.to_dict()
            if data.get("uid") != uid:
                logger.warning(
                    f"User {uid} attempted to delete dream job {dream_job_id} "
                    f"owned by {data.get('uid')}"
                )
                return False
            self.db.collection("dream_jobs").document(dream_job_id).delete()
            return True
        except Exception as e:
            logger.error(f"Error deleting dream job {dream_job_id}: {e}")
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
