from fastapi import FastAPI

app = FastAPI(title="AI Market Research Agent", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "component": "market-agent-m1"}
