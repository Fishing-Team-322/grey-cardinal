#!/bin/sh
# Render the sing-box config from the template, substituting ONLY the VPN
# secrets/hosts (so $-syntax inside the JSON is never touched) and run sing-box.
set -eu

: "${VPN_HY2_PASSWORD:?VPN_HY2_PASSWORD is required}"
: "${VPN_NODE_NL_HOST:?VPN_NODE_NL_HOST is required}"
: "${VPN_NODE_CH_HOST:?VPN_NODE_CH_HOST is required}"
: "${VPN_DUBAI_HOST:?VPN_DUBAI_HOST is required}"
: "${VPN_DUBAI_UUID:?VPN_DUBAI_UUID is required}"

export VPN_HY2_PASSWORD VPN_NODE_NL_HOST VPN_NODE_CH_HOST VPN_DUBAI_HOST VPN_DUBAI_UUID

envsubst '${VPN_HY2_PASSWORD} ${VPN_NODE_NL_HOST} ${VPN_NODE_CH_HOST} ${VPN_DUBAI_HOST} ${VPN_DUBAI_UUID}' \
  < /etc/sing-box/config.template.json \
  > /etc/sing-box/config.json

sing-box check -c /etc/sing-box/config.json
exec sing-box run -c /etc/sing-box/config.json
