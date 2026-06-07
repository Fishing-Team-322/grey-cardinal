# Outbound VPN egress for LLM traffic (Groq is geo-blocked from the RU server).
# sing-box dials foreign Hysteria2 exits and exposes a local mixed HTTP/SOCKS
# proxy on :8889. brain-api routes ONLY Groq through it via LLM_PROXY.
# sing-box isn't packaged in Alpine 3.20, so we fetch the official static binary.
FROM alpine:3.20
ARG SINGBOX_VERSION=1.13.13
RUN apk add --no-cache ca-certificates gettext \
 && apk add --no-cache --virtual .dl curl tar \
 && curl -fsSL "https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-amd64.tar.gz" -o /tmp/sb.tgz \
 && tar -xzf /tmp/sb.tgz -C /tmp \
 && mv "/tmp/sing-box-${SINGBOX_VERSION}-linux-amd64/sing-box" /usr/local/bin/sing-box \
 && chmod +x /usr/local/bin/sing-box \
 && rm -rf /tmp/sb.tgz /tmp/sing-box-* \
 && apk del .dl \
 && sing-box version
COPY config.template.json /etc/sing-box/config.template.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8889
ENTRYPOINT ["/entrypoint.sh"]
