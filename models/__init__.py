"""
SQLAlchemy ORM models for the filings database.
"""
from datetime import datetime
from typing import List

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer,
    String, Text, BigInteger, Numeric, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from config.db import Base


class Company(Base):
    """Company/ticker registry."""
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    cik = Column(String(10), nullable=False)  # Unique per active company (enforced by partial index)
    company_name = Column(String(255))
    exchange = Column(String(20), nullable=False)  # Increased to support 'NYSE American'
    is_active = Column(Boolean, default=True)
    status = Column(String(20), nullable=False, default='active')  # 'active' or 'merged'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filings = relationship("Filing", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('ticker', 'exchange', name='uq_ticker_exchange'),
        Index('idx_companies_cik', 'cik'),
        Index('idx_companies_ticker', 'ticker'),
        Index('idx_companies_status', 'status'),
    )


class ListingsRef(Base):
    """Exchange reference data from NASDAQ/NYSE listing files."""
    __tablename__ = 'listings_ref'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False)
    exchange_code = Column(String(10), nullable=False)
    exchange_name = Column(String(50), nullable=False)
    is_etf = Column(Boolean, default=False)
    source = Column(String(20), nullable=False)
    file_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('symbol', 'exchange_code', name='uq_symbol_exchange'),
        Index('idx_listings_ref_symbol', 'symbol'),
        Index('idx_listings_ref_exchange', 'exchange_code'),
        Index('idx_listings_ref_source', 'source'),
    )


class Filing(Base):
    """SEC filing metadata."""
    __tablename__ = 'filings'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='CASCADE'), nullable=False)
    accession_number = Column(String(25), nullable=False, unique=True)
    form_type = Column(String(10), nullable=False)
    filing_date = Column(Date, nullable=False)
    report_date = Column(Date)
    fiscal_year = Column(Integer, nullable=False)
    fiscal_period = Column(String(5))
    is_amendment = Column(Boolean, default=False)
    amends_accession = Column(String(25), ForeignKey('filings.accession_number', deferrable=True))
    primary_document = Column(String(255))
    document_count = Column(Integer)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    company = relationship("Company", back_populates="filings")
    artifacts = relationship("Artifact", back_populates="filing", cascade="all, delete-orphan")
    amendments = relationship("Filing", remote_side=[accession_number], backref="amended_filing")
    
    __table_args__ = (
        Index('idx_filings_company', 'company_id'),
        Index('idx_filings_date', 'filing_date'),
        Index('idx_filings_form_year', 'form_type', 'fiscal_year'),
        Index('idx_filings_accession', 'accession_number'),
    )


class Artifact(Base):
    """Downloaded artifact tracking."""
    __tablename__ = 'artifacts'
    
    id = Column(Integer, primary_key=True)
    filing_id = Column(Integer, ForeignKey('filings.id', ondelete='CASCADE'), nullable=False)
    artifact_type = Column(String(20), nullable=False)
    filename = Column(String(255), nullable=False)
    local_path = Column(String(512))
    url = Column(Text, nullable=False)
    file_size = Column(BigInteger)
    sha256 = Column(String(64))
    status = Column(String(20), default='pending_download')
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text)
    last_attempt_at = Column(DateTime)
    downloaded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    filing = relationship("Filing", back_populates="artifacts")
    retry_entry = relationship("RetryQueue", back_populates="artifact", uselist=False, cascade="all, delete-orphan")
    error_logs = relationship("ErrorLog", back_populates="artifact", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('filing_id', 'filename', name='uq_filing_filename'),
        Index('idx_artifacts_filing', 'filing_id'),
        Index('idx_artifacts_status', 'status'),
        Index('idx_artifacts_sha256', 'sha256'),
    )


class RetryQueue(Base):
    """Retry queue for failed artifacts."""
    __tablename__ = 'retry_queue'
    
    id = Column(Integer, primary_key=True)
    artifact_id = Column(Integer, ForeignKey('artifacts.id', ondelete='CASCADE'), nullable=False, unique=True)
    scheduled_for = Column(DateTime, nullable=False)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    artifact = relationship("Artifact", back_populates="retry_entry")
    
    __table_args__ = (
        Index('idx_retry_queue_schedule', 'scheduled_for', 'priority'),
    )


class ExecutionRun(Base):
    """Execution run audit trail."""
    __tablename__ = 'execution_runs'
    
    id = Column(Integer, primary_key=True)
    run_type = Column(String(50), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(20), nullable=False)
    filings_discovered = Column(Integer, default=0)
    artifacts_attempted = Column(Integer, default=0)
    artifacts_succeeded = Column(Integer, default=0)
    artifacts_failed = Column(Integer, default=0)
    duration_seconds = Column(Integer)
    error_summary = Column(Text)
    meta_data = Column('metadata', JSONB)  # Map to 'metadata' column (avoiding Python keyword)
    
    # Relationships
    error_logs = relationship("ErrorLog", back_populates="execution_run", cascade="all, delete-orphan")
    incremental_update = relationship("IncrementalUpdate", back_populates="execution_run", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_execution_runs_type', 'run_type', 'started_at'),
    )


class ErrorLog(Base):
    """Detailed error logging."""
    __tablename__ = 'error_logs'
    
    id = Column(Integer, primary_key=True)
    execution_run_id = Column(Integer, ForeignKey('execution_runs.id'))
    artifact_id = Column(Integer, ForeignKey('artifacts.id'))
    error_type = Column(String(50))
    error_message = Column(Text)
    stack_trace = Column(Text)
    occurred_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    execution_run = relationship("ExecutionRun", back_populates="error_logs")
    artifact = relationship("Artifact", back_populates="error_logs")
    
    __table_args__ = (
        Index('idx_error_logs_run', 'execution_run_id'),
        Index('idx_error_logs_artifact', 'artifact_id'),
        Index('idx_error_logs_type', 'error_type', 'occurred_at'),
    )


class IncrementalUpdate(Base):
    """Weekly incremental update tracking."""
    __tablename__ = 'incremental_updates'
    
    id = Column(Integer, primary_key=True)
    execution_run_id = Column(Integer, ForeignKey('execution_runs.id'), nullable=False, unique=True)
    lookback_start = Column(Date, nullable=False)
    lookback_end = Column(Date, nullable=False)
    companies_scanned = Column(Integer)
    new_filings_found = Column(Integer)
    sla_met = Column(Boolean)
    success_rate = Column(Numeric(5, 2))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    execution_run = relationship("ExecutionRun", back_populates="incremental_update")
    
    __table_args__ = (
        Index('idx_incremental_updates_date', 'lookback_end'),
    )
