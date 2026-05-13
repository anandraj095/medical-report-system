from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RejectedReport(Base):
    __tablename__ = "rejected_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id"), index=True, nullable=False)
    raw_row_id: Mapped[int | None] = mapped_column(ForeignKey("raw_report_rows.id"), nullable=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False)
    reason_details: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    upload = relationship("Upload", back_populates="rejected_reports")
