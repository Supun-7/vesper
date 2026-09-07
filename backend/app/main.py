"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.query_agent import answer_question
from app.agents.forecasting_agent import forecast_question

app = FastAPI(title="Vesper API", description="AI layer for legacy ERP systems")

# Allow the local React dev server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    return answer_question(request.question)


@app.post("/forecast")
def forecast(request: AskRequest):
    return forecast_question(request.question)
