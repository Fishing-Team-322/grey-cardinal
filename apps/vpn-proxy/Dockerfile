# Outbound VPN egress for LLM traffic (Groq is geo-blocked from the RU server).
# sing-box dials foreign Hysteria2 exits and exposes a local mixed HTTP/SOCKS
# proxy on :8889. brain-api routes ONLY Groq through it via LLM_PROXY.
# Mirrors the tg-proxy pattern: tiny Alpine image, secrets injected at runtime.
FROM alpine:3.20
RUN apk add --no-cache sing-box gettext ca-certificates
COPY config.template.json /etc/sing-box/config.template.json
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8889
ENTRYPOINT ["/entrypoint.sh"]
