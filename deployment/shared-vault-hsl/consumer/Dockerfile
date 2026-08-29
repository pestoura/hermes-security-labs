FROM hashicorp/vault:1.21.4@sha256:4e33b126a59c0c333b76fb4e894722462659a6bec7c48c9ee8cea56fccfd2569 AS vaultcli

FROM docker.io/library/python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322

RUN addgroup -S -g 10001 hslconsumer \
    && adduser -S -D -H -u 10001 -G hslconsumer hslconsumer

COPY --from=vaultcli /bin/vault /usr/local/bin/vault
RUN chown root:root /usr/local/bin/vault \
    && chmod 0555 /usr/local/bin/vault

USER 10001:10001
WORKDIR /tmp
ENTRYPOINT ["/bin/sh"]
CMD ["-c", "trap : TERM INT; sleep infinity & wait"]
