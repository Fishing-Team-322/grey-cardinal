#!/usr/bin/env bash
set -euo pipefail

docker stop ollama-test || true
docker rm ollama-test || true

echo "Old public ollama-test container removed if it existed."
echo "Now check externally that http://SERVER_IP:11434/api/tags is not accessible."
