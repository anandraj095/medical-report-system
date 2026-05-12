from sqlalchemy import Column, Float, Integer, String

from app.database import Base


class CBCReport(Base):
    __tablename__ = "cbc_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String(100), index=True, nullable=False)
    patient_name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(20), nullable=False)
    hemoglobin = Column(Float, nullable=False)
    wbc = Column(Float, nullable=False)
    platelets = Column(Float, nullable=False)
    test_date = Column(String(50), nullable=False)
    machine_id = Column(String(100), nullable=False)
