"""
Configuration settings for the filings ETL system.
Uses pydantic-settings for type-safe configuration from environment variables.
"""
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )
    
    # Database configuration
    db_host: str = Field(default="localhost", description="PostgreSQL host")
    db_port: int = Field(default=5432, description="PostgreSQL port")
    db_name: str = Field(default="filings_db", description="Database name")
    db_user: str = Field(default="postgres", description="Database user")
    db_password: str = Field(default="postgres", description="Database password")
    
    # Storage configuration
    storage_backend: str = Field(default="local", description="Storage backend: 'local' or 's3'")
    storage_root: str = Field(default="/data/filings", description="Root path for file storage")
    s3_bucket: Optional[str] = Field(default=None, description="S3 bucket name if using S3 backend")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    
    # SEC API configuration
    sec_user_agent: str = Field(
        default="MyCompany legal@example.com",
        description="User-Agent for SEC requests (REQUIRED - update with your info)"
    )
    sec_rate_limit: int = Field(default=10, description="Max requests per second to SEC")
    sec_timeout: int = Field(default=30, description="Request timeout in seconds")
    sec_retry_max: int = Field(default=3, description="Max retry attempts for failed requests")
    
    # ETL configuration
    max_workers: int = Field(default=10, description="Number of concurrent download workers (deprecated, use download_workers)")
    download_workers: int = Field(default=8, description="Number of concurrent download workers (1-10 due to SEC rate limit)")
    artifact_retry_max: int = Field(default=3, description="Max retries per artifact")
    incremental_lookback_days: int = Field(default=7, description="Days to look back for incremental updates")
    
    # SLA configuration
    sla_duration_hours: int = Field(default=6, description="Max hours for incremental run")
    sla_success_rate: float = Field(default=99.0, description="Minimum success rate percentage")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: 'json' or 'console'")
    
    @field_validator('sec_user_agent')
    @classmethod
    def validate_user_agent(cls, v: str) -> str:
        """Ensure User-Agent is properly configured."""
        if v == "MyCompany legal@example.com":
            raise ValueError(
                "SEC_USER_AGENT must be customized with your company name and email. "
                "Example: 'YourCompany contact@yourcompany.com'"
            )
        if '@' not in v:
            raise ValueError("SEC_USER_AGENT must include a valid email address")
        return v

    @field_validator('download_workers')
    @classmethod
    def validate_download_workers(cls, v: int) -> int:
        """Ensure download_workers is within safe limits."""
        if v < 1:
            raise ValueError("DOWNLOAD_WORKERS must be at least 1")
        if v > 10:
            raise ValueError(
                "DOWNLOAD_WORKERS must not exceed 10 due to SEC rate limit (10 req/s). "
                "Higher values won't improve performance and may violate rate limits."
            )
        return v
    
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return f"postgresql+psycopg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def sla_duration_seconds(self) -> int:
        """Convert SLA hours to seconds."""
        return self.sla_duration_hours * 3600


# Global settings instance
settings = Settings()
