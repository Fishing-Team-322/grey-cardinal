# Minimal outbound HTTP(S) CONNECT proxy for the Telegram bot.
# tinyproxy from Alpine (community repo). The reachable Telegram IP is pinned
# via docker-compose extra_hosts on this service.
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
EXPOSE 8888
# -d: run in foreground (required for the container's main process).
CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
