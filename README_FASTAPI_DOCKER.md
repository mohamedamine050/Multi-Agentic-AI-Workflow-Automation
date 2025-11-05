Quickstart — FastAPI service & Docker

1) Install dependencies locally (recommended to use venv):

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

2) Run the FastAPI service locally:

   uvicorn service:app --reload --host 0.0.0.0 --port 8000

3) Docker build & run:

   docker build -t chatbot-langgraph:latest .
   docker run --rm -p 8000:8000 chatbot-langgraph:latest

4) CI

A GitHub Actions workflow is provided at `.github/workflows/ci.yml`. It will:
 - install dependencies
 - run a Python syntax check
 - build the Docker image
 - run the container and curl `/health`

Notes:
 - The FastAPI service is intentionally lightweight (health/ready/info endpoints) so it doesn't interfere with your LangGraph runtime. If you want the FastAPI service to trigger runs or expose LangGraph internals, say so and I can wire it to `graph.app` safely.
