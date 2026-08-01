FROM docker.io/library/python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322

ARG LAB_ID
ARG LAB_MODE
ARG SOURCE_REPO
ARG SOURCE_COMMIT
ARG SOURCE_ARCHIVE_SHA256=""

ENV LAB_ID="${LAB_ID}" \
    LAB_MODE="${LAB_MODE}" \
    SOURCE_REPO="${SOURCE_REPO}" \
    SOURCE_COMMIT="${SOURCE_COMMIT}" \
    SOURCE_ARCHIVE_SHA256="${SOURCE_ARCHIVE_SHA256}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/hermes-lab
COPY fetch_source.py /opt/hermes-lab/fetch_source.py
RUN python /opt/hermes-lab/fetch_source.py && rm /opt/hermes-lab/fetch_source.py

COPY server.py /opt/hermes-lab/server.py
RUN addgroup -g 2000 -S hermeslab \
    && adduser -u 2000 -S -D -H -G hermeslab hermeslab \
    && chown -R 2000:2000 /opt/hermes-lab

USER 2000:2000
EXPOSE 8080 8090
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read(1)"]
ENTRYPOINT ["python", "/opt/hermes-lab/server.py"]
