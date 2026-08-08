FROM docker.io/library/python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322

RUN addgroup -S -g 10001 hermes \
    && adduser -S -D -H -u 10001 -G hermes hermes \
    && mkdir -p /opt/hermes/runners /var/tmp/hermes \
    && chown root:root /opt/hermes/runners \
    && chmod 0555 /opt/hermes/runners \
    && chown 10001:10001 /var/tmp/hermes

COPY --chown=root:root runtime_probe.py /opt/hermes/runners/runtime_probe.py
RUN chmod 0555 /opt/hermes/runners/runtime_probe.py

USER 10001:10001
WORKDIR /opt/hermes/runners
ENTRYPOINT ["python", "/opt/hermes/runners/runtime_probe.py"]
