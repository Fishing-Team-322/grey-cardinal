from pathlib import Path


def test_ollama_not_public_in_prod_compose():
    compose = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    ollama_block = compose.split("  ollama:", 1)[1].split("\n  asr-service:", 1)[0]

    assert "ports:" not in ollama_block
    assert 'expose:\n      - "11434"' in ollama_block
    assert "ollama_data:/root/.ollama" in ollama_block
