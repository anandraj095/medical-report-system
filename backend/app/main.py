from fastapi import FastAPI

from app.database import Base, engine
from app.models import CBCReport, RawReportRow, RejectedReport, SuspiciousFlag, Upload  # noqa: F401
from app.routers.analytics import router as analytics_router
from app.routers.reports import router as reports_router
from app.routers.uploads import router as uploads_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Medical Report Review & Exception Handling API")
app.include_router(uploads_router)
app.include_router(reports_router)
app.include_router(analytics_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {"message": "Medical Report Review backend is running."}
