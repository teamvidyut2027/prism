# Prism: Visual Task Factory, a self-contained runtime image.
#   docker build -t prism .
#   docker run --rm -p 8000:8000 prism                      # dashboard (builds prism-core on first start)
#   docker run --rm prism python -m prism reproduce         # judges: full rebuild + validation in one command
#   docker run --rm -e ANTHROPIC_API_KEY=... prism python -m prism eval --model anthropic:opus-5-5 --base-per-family 5
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PRISM_HOST=0.0.0.0 \
    PRISM_PORT=8000

# libglib2.0: needed by OpenCV's headless wheel.
# libfribidi0: lets Pillow's bundled Raqm/HarfBuzz text shaper load. Without it Pillow falls back to basic
# layout, kerning differs, and text-bearing images are no longer byte-identical to other platforms.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libfribidi0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# application code (the React dashboard is prebuilt into prism/static)
COPY prism ./prism
COPY tests ./tests
COPY docs ./docs
COPY data/datasets/prism-sample ./data/datasets/prism-sample
COPY docker-entrypoint.sh README.md ./
RUN chmod +x docker-entrypoint.sh && useradd -m prism && chown -R prism /app
USER prism

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["serve"]
