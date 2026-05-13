from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CBCReport(Base):
    __tablename__ = "cbc_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), index=True, nullable=False)
    source_row_id: Mapped[int | None] = mapped_column(ForeignKey("raw_report_rows.id"), nullable=True)
    row_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    patient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(1), nullable=False)
    hemoglobin: Mapped[float] = mapped_column(Float, nullable=False)
    wbc: Mapped[float] = mapped_column(Float, nullable=False)
    platelets: Mapped[float] = mapped_column(Float, nullable=False)
    test_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="reports")
    source_row = relationship("RawReportRow", back_populates="report")
    flags = relationship("SuspiciousFlag", back_populates="report", cascade="all, delete-orphan")
