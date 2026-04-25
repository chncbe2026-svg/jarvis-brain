import os

# Use Render's $PORT environment variable, default to 10000
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
