# LLM providers

Supported providers:

- `local`: OpenAI-compatible local endpoint, default `http://ollama:11434/v1`.
- `external_api`: OpenAI-compatible external API.

Resolution order:

1. Team-level `llm_settings`.
2. Company-level `llm_settings`.
3. Global environment settings.
4. Production readiness error.

Production forbids `LLM_PROVIDER=disabled`.

The semantic parser asks for strict JSON and retries invalid JSON up to the configured retry count. It does not silently switch to heuristic parsing in production.
