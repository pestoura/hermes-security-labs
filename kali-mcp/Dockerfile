# syntax=docker/dockerfile:1
ARG BASE_IMAGE=kalilinux/kali-rolling:latest
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

COPY patches/mcp_kali_server_20260317_list_compat.py /tmp/mcp_kali_server_20260317_list_compat.py

# No external APT repositories. No recommends. Cleanup afterwards.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      mcp-kali-server \
      nmap \
      gobuster \
      dirb \
      nikto \
      sqlmap \
      metasploit-framework \
      hydra \
      john \
      wpscan \
      enum4linux \
      enum4linux-ng \
      ffuf \
      wordlists \
      seclists \
      curl \
      wget \
      jq \
      file \
      procps \
      netcat-openbsd \
      ca-certificates && \
    python3 /tmp/mcp_kali_server_20260317_list_compat.py && \
    rm -f /tmp/mcp_kali_server_20260317_list_compat.py && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify persisted toolchain presence and the exact compatibility boundary.
RUN command -v kali-server-mcp && \
    command -v mcp-server && \
    command -v sqlmap && \
    command -v hydra && \
    command -v enum4linux && \
    command -v enum4linux-ng && \
    kali-server-mcp -h >/dev/null 2>&1 && \
    mcp-server -h >/dev/null 2>&1 && \
    dpkg-query -W -f='${Package} ${Version}\n' mcp-kali-server

USER root
WORKDIR /opt/kali
EXPOSE 5000
CMD ["kali-server-mcp", "--ip", "127.0.0.1", "--port", "5000"]
