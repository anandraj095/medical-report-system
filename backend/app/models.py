from sqlalchemy import Column, Integer, String
from .database import Base

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_name = Column(String(255))
    status = Column(String(50))