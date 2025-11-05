from fastapi import FastAPI
import os

app = FastAPI(title="chatbot-langgraph-service")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    # Basic readiness: check that important env vars are present (not strict)
    ok = True
    missing = []
    for v in ("GMAIL_USER", "GMAIL_APP_PASSWORD"):
        if not os.getenv(v):
            missing.append(v)
            ok = False
    return {"ready": ok, "missing_env": missing}

# Lightweight endpoint to show that the repository started the app module.
@app.get("/info")
def info():
    return {"project": "chatbot-langgraph", "service": "fastapi", "show_email_as_tool": os.getenv("SHOW_EMAIL_AS_TOOL", "false")}
