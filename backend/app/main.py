from fastapi import FastAPI

from app.database import Base, engine
from app.models import CBCReport  # noqa: F401
from app.routers.csv_upload import router as csv_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Medical Report System API")
app.include_router(csv_router)


@app.get("/")
def root():
    return {"message": "Medical Report System API is running"}
