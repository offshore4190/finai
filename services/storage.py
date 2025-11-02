"""
Storage service for managing filing artifacts on filesystem or cloud.
Implements abstract interface for easy migration to S3.
"""
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import structlog

from config.settings import settings

logger = structlog.get_logger()


class StorageAdapter(ABC):
    """Abstract storage adapter interface."""
    
    @abstractmethod
    def write(self, path: str, content: bytes) -> bool:
        """Write content to path."""
        pass
    
    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read content from path."""
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass
    
    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete file at path."""
        pass
    
    @abstractmethod
    def ensure_directory(self, directory: str) -> bool:
        """Ensure directory exists."""
        pass


class LocalFileSystemAdapter(StorageAdapter):
    """Local filesystem storage adapter."""
    
    def __init__(self, root_path: str):
        """
        Initialize local filesystem adapter.
        
        Args:
            root_path: Root directory for all storage
        """
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        logger.info("local_storage_initialized", root=str(self.root_path))
    
    def _get_full_path(self, path: str) -> Path:
        """Get full filesystem path."""
        return self.root_path / path
    
    def write(self, path: str, content: bytes) -> bool:
        """Write content to file."""
        full_path = self._get_full_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Use temporary file and atomic rename for safety
            temp_path = full_path.with_suffix('.tmp')
            temp_path.write_bytes(content)
            temp_path.replace(full_path)
            return True
        except Exception as e:
            logger.error("write_failed", path=path, error=str(e))
            return False
    
    def read(self, path: str) -> bytes:
        """Read content from file."""
        full_path = self._get_full_path(path)
        return full_path.read_bytes()
    
    def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self._get_full_path(path)
        return full_path.exists()
    
    def delete(self, path: str) -> bool:
        """Delete file."""
        full_path = self._get_full_path(path)
        try:
            if full_path.exists():
                full_path.unlink()
            return True
        except Exception as e:
            logger.error("delete_failed", path=path, error=str(e))
            return False
    
    def ensure_directory(self, directory: str) -> bool:
        """Ensure directory exists."""
        full_path = self._get_full_path(directory)
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error("mkdir_failed", directory=directory, error=str(e))
            return False


class StorageService:
    """
    High-level storage service for filing artifacts.
    Handles path construction and storage operations.
    """
    
    def __init__(self, adapter: Optional[StorageAdapter] = None):
        """
        Initialize storage service.
        
        Args:
            adapter: Storage adapter (defaults to local filesystem)
        """
        if adapter is None:
            adapter = LocalFileSystemAdapter(settings.storage_root)
        
        self.adapter = adapter
        logger.info("storage_service_initialized")
    
    def construct_path(
        self,
        exchange: str,
        ticker: str,
        fiscal_year: int,
        fiscal_period: str,
        filing_date_str: str,
        artifact_type: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Construct storage path following convention:
        {exchange}/{ticker}/{year}/{ticker}_{year}_{Qtag}_{DD-MM-YYYY}.{ext}
        
        Args:
            exchange: 'NASDAQ' or 'NYSE'
            ticker: Company ticker symbol
            fiscal_year: Fiscal year
            fiscal_period: 'FY', 'Q1', 'Q2', 'Q3', 'Q4'
            filing_date_str: Filing date in DD-MM-YYYY format
            artifact_type: 'html', 'image', 'xbrl_raw', 'xbrl_derived'
            filename: Original filename (for xbrl and images)
        
        Returns:
            Relative path string
        """
        base = f"{exchange}/{ticker}/{fiscal_year}"
        
        if artifact_type == 'html':
            return f"{base}/{ticker}_{fiscal_year}_{fiscal_period}_{filing_date_str}.html"
        
        elif artifact_type == 'image':
            # Extract extension from original filename
            ext = Path(filename).suffix if filename else '.png'
            # Image sequence will be added by caller
            return f"{base}/{ticker}_{fiscal_year}_{fiscal_period}_{filing_date_str}_{{seq}}{ext}"
        
        elif artifact_type.startswith('xbrl'):
            # Keep original filename in xbrl subdirectory
            return f"{base}/xbrl/{filename}"
        
        else:
            raise ValueError(f"Unknown artifact type: {artifact_type}")
    
    def save_artifact(self, path: str, content: bytes) -> bool:
        """
        Save artifact to storage.
        
        Args:
            path: Relative path
            content: File content
        
        Returns:
            Success boolean
        """
        return self.adapter.write(path, content)
    
    def artifact_exists(self, path: str) -> bool:
        """Check if artifact exists."""
        return self.adapter.exists(path)
    
    def ensure_directory_structure(self, exchange: str, ticker: str, year: int):
        """
        Ensure directory structure exists for a company/year.
        
        Args:
            exchange: Exchange name
            ticker: Ticker symbol
            year: Fiscal year
        """
        base_dir = f"{exchange}/{ticker}/{year}"
        xbrl_dir = f"{base_dir}/xbrl"
        
        self.adapter.ensure_directory(base_dir)
        self.adapter.ensure_directory(xbrl_dir)


# Global storage service instance
storage_service = StorageService()
