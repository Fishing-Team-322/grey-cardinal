# Ollama в production

В production Ollama должен быть доступен только внутри Docker network.

## Что изменено

- `docker-compose.prod.yml` использует `expose: 11434`, а не публичный `ports`.
- Brain API обращается к `http://ollama:11434/v1`.
- Старый публичный контейнер `ollama-test` должен быть удалён.

## Удаление старого публичного контейнера

```bash
cd /opt/grey-cardinal
bash scripts/ops/disable_public_ollama.sh
```

После удаления проверь с внешней машины:

```bash
curl -f http://SERVER_IP:11434/api/tags
```

Ожидаемый результат: соединение недоступно или порт закрыт.

## Rollback

Rollback не должен открывать порт 11434 наружу. Если нужен временный debug-доступ, используй SSH tunnel:

```bash
ssh -L 11434:localhost:11434 root@SERVER
```
