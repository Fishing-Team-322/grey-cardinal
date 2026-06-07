# Outbound VPN egress for LLM traffic (Groq is geo-blocked from the RU server).
# sing-box dials foreign Hysteria2 exits and exposes a local mixed HTTP/SOCKS
# proxy on :8889. brain-api routes ONLY Groq through it via LLM_PROXY.
# The official sing-box build is glibc-linked (ships libcronet.so), so we use a
# Debian base rather than Alpine/musl.
FROM debian:12-slim
ARG SINGBOX_VERSION=1.13.13
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates gettext-base curl \
 && curl -fsSL "https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-amd64.tar.gz" -o /tmp/sb.tgz \
 && tar -xzf /tmp/sb.tgz -C /tmp \
 && mv "/tmp/sing-box-${SINGBOX_VERSION}-linux-amd64/sing-box" /usr/local/bin/sing-box \
 && mv "/tmp/sing-box-${SINGBOX_VERSION}-linux-amd64/libcronet.so" /usr/local/lib/ \
 && chmod +x /usr/local/bin/sing-box \
 && rm -rf /tmp/sb.tgz /tmp/sing-box-* \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && ldconfig \
 && sing-box version
COPY config.template.json /etc/sing-box/config.template.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8889
ENTRYPOINT ["/entrypoint.sh"]
