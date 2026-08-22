FROM docker.io/library/python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322

RUN addgroup -S -g 10001 hslprobe \
    && adduser -S -D -H -u 10001 -G hslprobe hslprobe \
    && mkdir -p /opt/hsl-probe \
    && chown root:root /opt/hsl-probe \
    && chmod 0555 /opt/hsl-probe

COPY --chown=root:root probe.py /opt/hsl-probe/probe.py
RUN chmod 0555 /opt/hsl-probe/probe.py

USER 10001:10001
WORKDIR /opt/hsl-probe
ENTRYPOINT ["python", "/opt/hsl-probe/probe.py"]
CMD ["--hold"]
