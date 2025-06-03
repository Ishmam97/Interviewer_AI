import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from supabase import create_client, Client
from dataclasses import asdict
import streamlit as st
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SupabaseManager:
    """Handles all Supabase database operations with improved error handling"""
    
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            logger.error("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
        except Exception as e:
            logger.error(f"Failed to create Supabase client: {e}")
            raise
    
    def _handle_error(self, operation: str, error: Exception) -> Dict[str, Any]:
        """Centralized error handling"""
        error_msg = str(error)
        logger.error(f"Error in {operation}: {error_msg}")
        
        # Parse Supabase errors for better user feedback
        if "PGRST204" in error_msg:
            return {"success": False, "error": "Database schema mismatch. Please contact support."}
        elif "JWT" in error_msg:
            return {"success": False, "error": "Authentication expired. Please sign in again."}
        elif "duplicate key" in error_msg.lower():
            return {"success": False, "error": "Record already exists."}
        else:
            return {"success": False, "error": f"Database error: {error_msg}"}
    
    def sign_up(self, email: str, password: str, full_name: str = "") -> Dict[str, Any]:
        """Sign up a new user"""
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": full_name
                    }
                }
            })
            return {"success": True, "user": response.user, "session": response.session}
        except Exception as e:
            return self._handle_error("sign_up", e)
    
    def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """Sign in an existing user"""
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            return {"success": True, "user": response.user, "session": response.session}
        except Exception as e:
            return self._handle_error("sign_in", e)
    
    def sign_out(self) -> Dict[str, Any]:
        """Sign out the current user"""
        try:
            self.client.auth.sign_out()
            return {"success": True}
        except Exception as e:
            return self._handle_error("sign_out", e)
    
    def get_current_user(self):
        """Get the current authenticated user"""
        try:
            return self.client.auth.get_user()
        except Exception as e:
            logger.error(f"Error getting current user: {e}")
            return None
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile by ID"""
        try:
            response = self.client.table('profiles').select('*').eq('id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching user profile: {e}")
            return None
    
    def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """Update user profile"""
        try:
            # Add updated_at timestamp
            profile_data['updated_at'] = datetime.now().isoformat()
            
            response = self.client.table('profiles').update(profile_data).eq('id', user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error updating user profile: {e}")
            return False
    
    def get_user_settings(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user settings"""
        try:
            response = self.client.table('user_settings').select('*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            else:
                # Create default settings if none exist
                default_settings = {
                    'user_id': user_id,
                    'max_questions': 5,
                    'model_name': 'gpt-4o-mini',
                    'temperature': 0.3,
                    'chunk_size': 500,
                    'chunk_overlap': 50
                }
                self.client.table('user_settings').insert(default_settings).execute()
                return default_settings
        except Exception as e:
            logger.error(f"Error fetching user settings: {e}")
            # Return default settings on error
            return {
                'max_questions': 5,
                'model_name': 'gpt-4o-mini',
                'temperature': 0.3,
                'chunk_size': 500,
                'chunk_overlap': 50
            }
    
    def update_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Update user settings with better error handling"""
        try:
            # Add timestamps
            settings['updated_at'] = datetime.now().isoformat()
            
            # Try to update first
            response = self.client.table('user_settings').update(settings).eq('user_id', user_id).execute()
            
            # If no rows affected, insert new settings
            if not response.data:
                settings['user_id'] = user_id
                settings['created_at'] = datetime.now().isoformat()
                response = self.client.table('user_settings').insert(settings).execute()
            
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            # Try with minimal settings if full update fails
            try:
                minimal_settings = {
                    'user_id': user_id,
                    'max_questions': settings.get('max_questions', 5),
                    'updated_at': datetime.now().isoformat()
                }
                response = self.client.table('user_settings').upsert(minimal_settings).execute()
                return len(response.data) > 0
            except:
                return False
    
    def create_interview_session(self, user_id: str, session_data: Dict[str, Any]) -> Optional[str]:
        """Create a new interview session with improved error handling"""
        try:
            # Prepare session data with required fields
            safe_session_data = {
                'user_id': user_id,
                'title': session_data.get('title', f"Interview Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
                'status': session_data.get('status', 'in_progress'),
                'interview_plan': session_data.get('interview_plan', []),
                'current_question_idx': session_data.get('current_question_idx', 0),
                'interview_notes': session_data.get('interview_notes', []),
                'conversation_history': session_data.get('conversation_history', []),
                'resume_content': session_data.get('resume_content', ''),
                'job_description': session_data.get('job_description', ''),
                'total_questions': session_data.get('total_questions', 0),
                'average_score': session_data.get('average_score'),
                'final_report': session_data.get('final_report', ''),
                'created_at': datetime.now().isoformat()
            }
            
            response = self.client.table('interview_sessions').insert(safe_session_data).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            logger.error(f"Error creating interview session: {e}")
            # Try with minimal data if full insert fails
            try:
                minimal_data = {
                    'user_id': user_id,
                    'status': 'in_progress',
                    'created_at': datetime.now().isoformat()
                }
                response = self.client.table('interview_sessions').insert(minimal_data).execute()
                return response.data[0]['id'] if response.data else None
            except:
                return None
    
    def update_interview_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Update an existing interview session"""
        try:
            # Prepare safe update data
            safe_session_data = {
                'updated_at': datetime.now().isoformat()
            }
            
            # Only include fields that exist in the schema
            field_mapping = {
                'status': 'status',
                'interview_plan': 'interview_plan',
                'current_question_idx': 'current_question_idx',
                'interview_notes': 'interview_notes',
                'conversation_history': 'conversation_history',
                'resume_content': 'resume_content',
                'job_description': 'job_description',
                'total_questions': 'total_questions',
                'average_score': 'average_score',
                'final_report': 'final_report',
                'title': 'title'
            }
            
            for key, db_field in field_mapping.items():
                if key in session_data:
                    safe_session_data[db_field] = session_data[key]
            
            response = self.client.table('interview_sessions').update(safe_session_data).eq('id', session_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error updating interview session: {e}")
            return False
    
    def get_interview_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get interview session by ID"""
        try:
            response = self.client.table('interview_sessions').select('*').eq('id', session_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching interview session: {e}")
            return None
    
    def get_user_interview_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all interview sessions for a user"""
        try:
            response = (self.client.table('interview_sessions')
                       .select('*')
                       .eq('user_id', user_id)
                       .order('created_at', desc=True)
                       .limit(limit)
                       .execute())
            return response.data
        except Exception as e:
            logger.error(f"Error fetching user interview sessions: {e}")
            return []
    
    def delete_interview_session(self, session_id: str) -> bool:
        """Delete an interview session"""
        try:
            response = self.client.table('interview_sessions').delete().eq('id', session_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting interview session: {e}")
            return False
    
    def save_interview_report(self, user_id: str, session_id: Optional[str], report_data: Dict[str, Any]) -> Optional[str]:
        """Save an interview report"""
        try:
            # Ensure report_content is provided as it's NOT NULL in the schema
            report_content = report_data.get('report_content', '')
            if not report_content:
                logger.error("Attempted to save report with empty content.")
                # Depending on desired behavior, you might return None or raise an error.
                # For now, this log will highlight the issue, Supabase will raise error on insert if empty.
                # Consider adding explicit error return: return None (and app.py should check for it)

            safe_report_data = {
                'user_id': user_id,
                'session_id': session_id, # This will be None if session_id is None
                'title': report_data.get('title', f"Interview Report {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
                'report_content': report_content, # report_content must be non-empty
                'summary': report_data.get('summary', {}), # Default to empty dict for JSONB
                'scores': report_data.get('scores', {}),   # Default to empty dict for JSONB
                'recommendations': report_data.get('recommendations', ''),
                'created_at': datetime.now().isoformat()
                # updated_at is handled by a database trigger
            }
            
            response = self.client.table('interview_reports').insert(safe_report_data).execute()
            
            if response.data:
                return response.data[0]['id']
            else:
                # Log the actual error from Supabase if available in response.error
                if hasattr(response, 'error') and response.error:
                    logger.error(f"Supabase error saving report: {response.error.message if hasattr(response.error, 'message') else response.error}")
                else:
                    logger.error("Failed to save interview report, no data returned and no specific Supabase error info.")
                return None
        except Exception as e:
            logger.error(f"Exception in save_interview_report: {e}")
            return None
    
    def get_user_reports(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all reports for a user"""
        try:
            response = (self.client.table('interview_reports')
                       .select('id, title, created_at')
                       .eq('user_id', user_id)
                       .order('created_at', desc=True)
                       .limit(limit)
                       .execute())
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching user reports: {e}")
            return []
    
    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report by ID"""
        try:
            response = self.client.table('interview_reports').select('*').eq('id', report_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching report: {e}")
            return None
    
    def delete_report(self, report_id: str) -> bool:
        """Delete a report"""
        try:
            response = self.client.table('interview_reports').delete().eq('id', report_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting report: {e}")
            return False

    def get_user_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard statistics for a user"""
        try:
            # Get session stats
            sessions_response = (self.client.table('interview_sessions')
                               .select('id, status, average_score, total_questions, created_at, title')
                               .eq('user_id', user_id)
                               .execute())
            
            sessions = sessions_response.data
            
            # Calculate stats
            total_sessions = len(sessions)
            completed_sessions = len([s for s in sessions if s.get('status') == 'completed'])
            
            if completed_sessions > 0:
                avg_scores = [s.get('average_score', 0) for s in sessions if s.get('average_score') is not None]
                overall_avg_score = sum(avg_scores) / len(avg_scores) if avg_scores else 0
                total_questions_answered = sum([s.get('total_questions', 0) for s in sessions if s.get('total_questions')])
            else:
                overall_avg_score = 0
                total_questions_answered = 0
            
            # Get recent activity (last 30 days)
            from datetime import datetime, timedelta
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            recent_sessions = [s for s in sessions if s.get('created_at', '') >= thirty_days_ago]
            
            return {
                'total_sessions': total_sessions,
                'completed_sessions': completed_sessions,
                'in_progress_sessions': len([s for s in sessions if s.get('status') == 'in_progress']),
                'overall_avg_score': round(overall_avg_score, 1) if overall_avg_score else 0,
                'total_questions_answered': total_questions_answered,
                'recent_activity': len(recent_sessions),
                'sessions': sessions[:10]  # Last 10 sessions for display
            }
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return {
                'total_sessions': 0,
                'completed_sessions': 0,
                'in_progress_sessions': 0,
                'overall_avg_score': 0,
                'total_questions_answered': 0,
                'recent_activity': 0,
                'sessions': []
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """Test database connection and schema"""
        try:
            # Test basic connection
            user = self.get_current_user()
            
            # Test table access
            tables_to_test = ['profiles', 'user_settings', 'interview_sessions', 'interview_reports']
            accessible_tables = []
            
            for table in tables_to_test:
                try:
                    self.client.table(table).select('id').limit(1).execute()
                    accessible_tables.append(table)
                except Exception as e:
                    logger.warning(f"Table {table} not accessible: {e}")
            
            return {
                'success': True,
                'user_authenticated': user is not None,
                'accessible_tables': accessible_tables,
                'total_tables': len(accessible_tables)
            }
        except Exception as e:
            return self._handle_error("test_connection", e)