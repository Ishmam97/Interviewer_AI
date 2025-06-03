import os
import json
from typing import Optional
from dataclasses import dataclass, asdict
from src.core.models import InterviewConfig


@dataclass
class SystemConfig:
    """Extended system configuration"""
    # Core settings
    interview: InterviewConfig
    
    # File paths
    default_resume_path: str = "data/resumes/resume.pdf"
    default_job_desc_path: str = "data/job_descriptions/job_desc.txt"
    
    # Output directories
    reports_dir: str = "./reports"
    sessions_dir: str = "./interview_sessions"
    logs_dir: str = "./logs"
    
    # System settings
    auto_save_sessions: bool = True
    max_log_age_days: int = 30
    enable_logging: bool = True
    log_level: str = "INFO"
    
    # Advanced settings
    retry_attempts: int = 3
    timeout_seconds: int = 30
    batch_size: int = 10


class ConfigManager:
    """Manages configuration loading, saving, and validation"""
    
    def __init__(self, config_path: str = "./config.json"):
        self.config_path = config_path
        self._config: Optional[SystemConfig] = None
    
    def load_config(self) -> SystemConfig:
        """Load configuration from file or create default"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config_dict = json.load(f)
                
                # Convert nested dicts back to dataclasses
                interview_config = InterviewConfig(**config_dict.get('interview', {}))
                
                config_dict['interview'] = interview_config
                self._config = SystemConfig(**config_dict)
                
                print(f"✅ Configuration loaded from {self.config_path}")
                
            except Exception as e:
                print(f"⚠️ Error loading config: {e}")
                print("Using default configuration")
                self._config = self._get_default_config()
        else:
            print("No config file found, creating default configuration")
            self._config = self._get_default_config()
            self.save_config()
        
        return self._config
    
    def save_config(self) -> None:
        """Save current configuration to file"""
        if not self._config:
            self._config = self._get_default_config()
        
        try:
            # Convert dataclasses to dict for JSON serialization
            config_dict = asdict(self._config)
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config_dict, f, indent=2)
            
            print(f"✅ Configuration saved to {self.config_path}")
            
        except Exception as e:
            print(f"❌ Error saving config: {e}")
    
    def get_config(self) -> SystemConfig:
        """Get current configuration"""
        if not self._config:
            return self.load_config()
        return self._config
    
    def update_config(self, **kwargs) -> None:
        """Update configuration parameters"""
        if not self._config:
            self._config = self.load_config()
        
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
            else:
                print(f"⚠️ Unknown config parameter: {key}")
        
        self.save_config()
    
    def _get_default_config(self) -> SystemConfig:
        """Get default configuration"""
        return SystemConfig(
            interview=InterviewConfig(
                max_questions=3,
                chunk_size=800,
                chunk_overlap=150,
                rag_k_results=3,
                temperature=0.3,
                model_name="gpt-4.1-nano-2025-04-14",
                index_path="./vector_stores/interview_faiss_index"
            ),
            default_resume_path="data/resumes/resume.pdf",
            default_job_desc_path="data/job_descriptions/job_desc.txt",
            reports_dir="./reports",
            sessions_dir="./interview_sessions",
            logs_dir="./logs",
            auto_save_sessions=True,
            max_log_age_days=30,
            enable_logging=True,
            log_level="INFO",
            retry_attempts=3,
            timeout_seconds=30,
            batch_size=10
        )
    
    def validate_config(self) -> bool:
        """Validate current configuration"""
        config = self.get_config()
        
        # Validate paths
        required_dirs = [
            config.reports_dir,
            config.sessions_dir,
            config.logs_dir
        ]
        
        for directory in required_dirs:
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                print(f"❌ Cannot create directory {directory}: {e}")
                return False
        
        # Validate interview config
        if config.interview.max_questions <= 0:
            print("❌ max_questions must be positive")
            return False
        
        if config.interview.chunk_size <= 0:
            print("❌ chunk_size must be positive")
            return False
        
        if config.interview.temperature < 0 or config.interview.temperature > 2:
            print("❌ temperature must be between 0 and 2")
            return False
        
        print("✅ Configuration is valid")
        return True
    
    def print_config(self) -> None:
        """Print current configuration"""
        config = self.get_config()
        
        print("\n" + "="*50)
        print("CURRENT CONFIGURATION")
        print("="*50)
        
        print("\n📋 Interview Settings:")
        print(f"  Max Questions: {config.interview.max_questions}")
        print(f"  Model: {config.interview.model_name}")
        print(f"  Temperature: {config.interview.temperature}")
        print(f"  Chunk Size: {config.interview.chunk_size}")
        print(f"  RAG Results: {config.interview.rag_k_results}")
        
        print("\n📁 File Paths:")
        print(f"  Resume: {config.default_resume_path}")
        print(f"  Job Description: {config.default_job_desc_path}")
        print(f"  FAISS Index: {config.interview.index_path}")
        
        print("\n📂 Output Directories:")
        print(f"  Reports: {config.reports_dir}")
        print(f"  Sessions: {config.sessions_dir}")
        print(f"  Logs: {config.logs_dir}")
        
        print("\n⚙️ System Settings:")
        print(f"  Auto Save Sessions: {config.auto_save_sessions}")
        print(f"  Enable Logging: {config.enable_logging}")
        print(f"  Log Level: {config.log_level}")
        print(f"  Retry Attempts: {config.retry_attempts}")


# Global config manager instance
config_manager = ConfigManager()


def get_config() -> SystemConfig:
    """Get the global configuration"""
    return config_manager.get_config()


def update_config(**kwargs) -> None:
    """Update the global configuration"""
    config_manager.update_config(**kwargs)


def validate_environment() -> bool:
    """Validate the environment and configuration"""
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        return False
    
    # Validate config
    if not config_manager.validate_config():
        return False
    
    print("✅ Environment validation passed")
    return True