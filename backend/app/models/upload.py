from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False, default="RECEIVED")
    duplicate_of_upload_id: Mapped[int | None] = mapped_column(ForeignKey("uploads.id"), nullable=True)
    original_headers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_rows_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deduplicated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suspicious_reports_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    raw_rows = relationship("RawReportRow", back_populates="upload", cascade="all, delete-orphan")
    rejected_reports = relationship("RejectedReport", back_populates="upload", cascade="all, delete-orphan")
    reports = relationship("CBCReport", back_populates="upload", cascade="all, delete-orphan")
    flags = relationship("SuspiciousFlag", back_populates="upload", cascade="all, delete-orphan")
    duplicate_of = relationship("Upload", remote_side=[id], uselist=False)
