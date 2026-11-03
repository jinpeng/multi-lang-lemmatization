FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Pinned so a rebuild months later produces the same wheels.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install \
      "fastapi==0.162.0" "uvicorn[standard]==0.54.0" "pydantic==2.14.2" \
      "sqlalchemy==2.1.6" "cryptography==50.0.2" "argon2-cffi==25.1.0" \
      "simplemma==2.0.0" "lemminflect==0.2.3" \
      "pymorphy3==2.0.6" "pymorphy3-dicts-ru==2.4.417150.4580142" \
      "sudachipy==0.7.0" "sudachidict_core==20261015" \
      "kiwipiepy==0.24.1" "kiwipiepy_model==0.24.0"

COPY api ./api

# Refuse to run insecurely: auth must be on in any image built from this file.
ENV LEMMA_AUTH_ENABLED=1 LEMMA_REQUIRE_AUTH=1

RUN useradd --create-home --uid 10001 lemma && mkdir -p /data && chown lemma /data
USER lemma
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health').status==200 else 1)"

# Every worker is a separate process and loads all seven backends: measured
# ~820 MB RSS each (ko ~357 MB, ja ~82 MB, ru ~36 MB, en ~16 MB, de/fr/es ~7 MB,
# rest = interpreter + numpy). 4 workers would need ~3.3 GB. Default to 2 and
# make it overridable rather than baking in a number that OOMs small hosts.
ENV LEMMA_WORKERS=2
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers ${LEMMA_WORKERS}"]
