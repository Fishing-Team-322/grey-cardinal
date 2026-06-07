#!/usr/bin/env python3
"""Eval-прогон русского semantic-парсера через реальный LLM-провайдер.

Скрипт берёт тот же промпт и ту же Pydantic-схему, что и production-парсер,
и гоняет набор размеченных русских сообщений (``evals/semantic_messages_ru.jsonl``)
через выбранный провайдер/модель. Печатает: model, provider, total, accuracy,
valid_json_rate, p50/p95 latency, errors, 429_count, timeout_count.

Ключи берутся ТОЛЬКО из окружения и никогда не печатаются (redact_secret).

Примеры:

    # Groq primary, несколько моделей
    GROQ_API_KEY=... python scripts/eval/semantic_llm_eval.py \\
        --provider groq \\
        --models llama-3.3-70b-versatile qwen/qwen3-32b llama-3.1-8b-instant

    # OpenRouter fallback
    OPENROUTER_API_KEY=... python scripts/eval/semantic_llm_eval.py \\
        --provider openrouter --models deepseek/deepseek-chat-v3:free

    # Локальная Ollama (dev)
    python scripts/eval/semantic_llm_eval.py \\
        --provider ollama --models qwen2.5:3b --base-url http://localhost:11434/v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

# Сделать пакеты brain-api и contracts импортируемыми при запуске из корня репо.
_REPO = Path(__file__).resolve().parents[2]
for _p in (_REPO / "apps" / "brain-api" / "src", _REPO / "packages" / "contracts" / "python"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pydantic import ValidationError  # noqa: E402

from brain_api.application.llm.schema import SemanticParseResult, semantic_json_schema  # noqa: E402
from brain_api.infrastructure.llm.errors import (  # noqa: E402
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from brain_api.infrastructure.llm.prompts import build_semantic_prompt  # noqa: E402
from brain_api.infrastructure.llm.providers import (  # noqa: E402
    LLMProviderConfig,
    OpenAICompatibleJSONProvider,
)
from brain_api.infrastructure.llm.redaction import redact_secret  # noqa: E402

DEFAULT_DATASET = _REPO / "apps" / "brain-api" / "evals" / "semantic_messages_ru.jsonl"

# Пресеты провайдеров: base_url + переменные окружения с ключом.
PRESETS: dict[str, dict[str, object]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_envs": ["GROQ_API_KEY", "LLM_EXTERNAL_API_KEY"],
        "needs_key": True,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_envs": ["OPENROUTER_API_KEY", "LLM_FALLBACK_API_KEY"],
        "needs_key": True,
    },
    "ollama": {
        "base_url": os.getenv("LLM_LOCAL_BASE_URL", "http://localhost:11434/v1"),
        "key_envs": [],
        "needs_key": False,
    },
    "external_api": {
        "base_url": os.getenv("LLM_EXTERNAL_BASE_URL", ""),
        "key_envs": ["LLM_EXTERNAL_API_KEY", "LLM_API_KEY"],
        "needs_key": True,
    },
}


def _first_env(names: list[str]) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def load_dataset(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


async def eval_model(
    provider_name: str,
    base_url: str,
    api_key: str,
    model: str,
    dataset: list[dict],
    *,
    timeout: int,
    max_retries: int,
    use_schema: bool,
) -> dict:
    config = LLMProviderConfig(
        provider="local" if provider_name == "ollama" else "external_api",
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout,
        max_retries=max_retries,
        strict_json=True,
    )
    provider = OpenAICompatibleJSONProvider(config)
    json_schema = semantic_json_schema() if use_schema else None
    now = datetime.now(UTC)

    total = len(dataset)
    correct = 0
    valid_json = 0
    errors = 0
    rate_limited = 0
    timeouts = 0
    latencies: list[float] = []

    for row in dataset:
        text = row["text"]
        expected = row.get("expected_kind")
        prompt = build_semantic_prompt(text, now, "Europe/Moscow")
        started = datetime.now(UTC)
        try:
            raw = await provider.complete_json(
                prompt, "semantic_message_v2", json_schema=json_schema
            )
        except LLMTimeoutError:
            errors += 1
            timeouts += 1
            continue
        except LLMRateLimitError:
            errors += 1
            rate_limited += 1
            continue
        except LLMError:
            errors += 1
            continue
        latencies.append((datetime.now(UTC) - started).total_seconds() * 1000)
        try:
            parsed = SemanticParseResult.model_validate(raw)
        except ValidationError:
            continue
        valid_json += 1
        if parsed.kind == expected:
            correct += 1

    def pct(part: int) -> float:
        return round(part / total, 4) if total else 0.0

    def percentile(values: list[float], q: float) -> int:
        if not values:
            return 0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
        return int(ordered[idx])

    return {
        "model": model,
        "provider": provider_name,
        "total": total,
        "accuracy": pct(correct),
        "valid_json_rate": pct(valid_json),
        "p50_latency_ms": int(statistics.median(latencies)) if latencies else 0,
        "p95_latency_ms": percentile(latencies, 0.95),
        "errors": errors,
        "429_count": rate_limited,
        "timeout_count": timeouts,
    }


def print_report(report: dict) -> None:
    print("─" * 52)
    print(f"  model            : {report['model']}")
    print(f"  provider         : {report['provider']}")
    print(f"  total            : {report['total']}")
    print(f"  accuracy         : {report['accuracy']:.2%}")
    print(f"  valid_json_rate  : {report['valid_json_rate']:.2%}")
    print(f"  p50_latency_ms   : {report['p50_latency_ms']}")
    print(f"  p95_latency_ms   : {report['p95_latency_ms']}")
    print(f"  errors           : {report['errors']}")
    print(f"  429_count        : {report['429_count']}")
    print(f"  timeout_count    : {report['timeout_count']}")


async def main_async(args: argparse.Namespace) -> int:
    preset = PRESETS.get(args.provider)
    if preset is None:
        print(f"Unknown provider: {args.provider}. Known: {', '.join(PRESETS)}", file=sys.stderr)
        return 2
    base_url = args.base_url or str(preset["base_url"])
    if not base_url:
        print("Base URL is empty — pass --base-url or set the env var.", file=sys.stderr)
        return 2
    api_key = _first_env(list(preset["key_envs"]))  # type: ignore[arg-type]
    if preset["needs_key"] and not api_key:
        envs = ", ".join(preset["key_envs"])  # type: ignore[arg-type]
        print(f"API key not found. Set one of: {envs}", file=sys.stderr)
        return 2

    dataset = load_dataset(args.dataset, args.limit)
    print(
        f"Dataset: {args.dataset} ({len(dataset)} examples) | "
        f"provider={args.provider} base_url={base_url} key={redact_secret(api_key) or '<none>'}"
    )

    reports = []
    for model in args.models:
        report = await eval_model(
            args.provider, base_url, api_key, model, dataset,
            timeout=args.timeout, max_retries=args.max_retries,
            use_schema=not args.no_schema,
        )
        print_report(report)
        reports.append(report)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nWrote JSON report to {args.json_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Russian semantic-parser LLM eval")
    parser.add_argument("--provider", required=True, choices=sorted(PRESETS))
    parser.add_argument("--models", required=True, nargs="+", help="One or more model ids")
    parser.add_argument("--base-url", default="", help="Override provider base URL")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of examples")
    parser.add_argument(
        "--no-schema", action="store_true",
        help="Use json_object instead of json_schema response_format",
    )
    parser.add_argument("--json-out", default="", help="Optional path to write JSON report")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
