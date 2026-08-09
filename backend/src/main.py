from fastapi import FastAPI

app = FastAPI(title="CODEX Hackfest 2026 Starter API")


@app.get("/")
def read_root():
    """Basic health/hello endpoint. Replace with your real API routes."""
    return {"message": "Hello World"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
