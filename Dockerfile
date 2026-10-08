FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 P95_BIND=0.0.0.0 P95_DATA_DIR=/data
RUN groupadd --gid 10001 explorer && useradd --uid 10001 --gid explorer --no-create-home explorer && mkdir /data && chown explorer:explorer /data
WORKDIR /srv
COPY --chown=explorer:explorer app ./app
USER explorer
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"
CMD ["python", "-m", "app.server"]
