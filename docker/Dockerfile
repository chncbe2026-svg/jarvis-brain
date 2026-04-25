FROM python:3.10-slim

WORKDIR /app

# System deps for sentence-transformers (torch)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding and reranker models so the container is self-contained
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='nomic-ai/nomic-embed-text-v1.5')"
RUN python -c "from fastembed import CrossEncoder; CrossEncoder(model_name='mixedbread-ai/mxbai-rerank-large-v1')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
