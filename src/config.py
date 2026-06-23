"""Configuration settings for the temporal agent benchmark."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""
    
    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key")
    
    # Model Configuration
    default_model: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model for agent"
    )
    
    # YOLO Configuration
    yolo_model: str = Field(
        default="yolo11n.pt",
        description="YOLO model weights file"
    )
    yolo_confidence_threshold: float = Field(
        default=0.5,
        description="Minimum confidence for YOLO detections"
    )
    
    # Trigger Configuration
    fixed_trigger_interval: int = Field(
        default=100,
        description="Frames between fixed trigger invocations"
    )
    event_trigger_cooldown: float = Field(
        default=2.0,
        description="Seconds before same object class can re-trigger"
    )
    
    # Cache Configuration
    cache_dir: str = Field(
        default=".cache",
        description="Directory for detection cache"
    )
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global settings instance
settings = Settings()
