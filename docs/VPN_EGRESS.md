# VPN egress for LLM (Groq)

The production server is in Moscow (RU). Groq blocks Russian IPs (`HTTP 403`),
so Groq traffic must exit through a foreign IP. OpenRouter, by contrast, is
reachable from RU directly (`HTTP 200`).

## Design

```
brain-api ──Groq (primary)────► LLM_PROXY=http://vpn-proxy:8889 ──► sing-box
                                                                    ├─ hysteria2 🇳🇱 ┐ urltest
                                                                    └─ hysteria2 🇨🇭 ┘ auto-failover
          ──OpenRouter (fallback)─► DIRECT (LLM_FALLBACK_PROXY empty)
          ──Ollama (local)────────► internal container (last resort)
```

- `apps/vpn-proxy` — Alpine + `sing-box`. Dials the foreign Hysteria2 exits from
  the VPN subscription and exposes a local mixed HTTP/SOCKS proxy on `:8889`.
  Two nodes (NL + CH) sit behind a `urltest` group, so a dead node fails over
  automatically.
- Only Groq is proxied (`LLM_PROXY`). The OpenRouter fallback is deliberately
  **direct** (`LLM_FALLBACK_PROXY` empty), so an LLM stays available even if the
  whole VPN is down. Ollama is the final floor.

## Configuration (`.env.production`)

```
LLM_PROXY=http://vpn-proxy:8889
LLM_FALLBACK_PROXY=                       # empty = direct
VPN_HY2_PASSWORD=<subscription UUID>      # the secret after hysteria2://
VPN_NODE_NL_HOST=nl01-ntr-hy01.tcp-reset-club.net
VPN_NODE_CH_HOST=che01-plr-hy01.tcp-reset-club.net
```

Only foreign exit nodes work. The second subscription (madrigal) has only `[RU]`
exits and therefore cannot bypass Groq's geo-block — it is not used here.

## Verify

```bash
# proxy reaches Groq from a foreign IP
docker compose -f docker-compose.prod.yml exec vpn-proxy \
  sh -c 'apk add --no-cache curl >/dev/null 2>&1; \
         curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 \
         -x http://127.0.0.1:8889 https://api.groq.com/openai/v1/models'
# expect 401 (reachable, needs key) — NOT 403 (geo-blocked)

curl -s https://fishingteam.su/health/llm   # primary provider health
```

## Rotating / updating nodes

The subscription is at `https://sub-001.aipulse.stream/api/sub/...`. To refresh
hosts/password, decode it (`curl ... | base64 -d`), pick the `hysteria2://`
foreign entries, update the `VPN_*` vars in `.env.production`, and
`docker compose -f docker-compose.prod.yml up -d --build vpn-proxy`.
