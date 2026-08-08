FROM python:3.12-alpine3.22@sha256:a190708a2dec1bd18b1decb539f8e8f5407abaa9bf39cacda583f7f8c11db322
RUN apk add --no-cache samba samba-common-tools && \
    mkdir -p /srv/controlled-share /run/samba && \
    printf '%s\n' 'synthetic lab data' > /srv/controlled-share/README.txt && \
    chmod 0755 /srv/controlled-share
COPY smb.conf /etc/samba/smb.conf
EXPOSE 445
ENTRYPOINT ["smbd", "--foreground", "--no-process-group", "--debug-stdout"]
