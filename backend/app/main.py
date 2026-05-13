from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.models import CBCReport, RawReportRow, RejectedReport, SuspiciousFlag, Upload  # noqa: F401
from app.routers.analytics import router as analytics_router
from app.routers.reports import router as reports_router
from app.routers.uploads import router as uploads_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Medical Report Review & Exception Handling API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173", 
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads_router)
app.include_router(reports_router)
app.include_router(analytics_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {"message": "Medical Report Review backend is running."}
