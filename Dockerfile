FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
