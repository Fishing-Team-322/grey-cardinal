"""
YouGile Integration Setup
=========================
Помогает найти все нужные ID для интеграции с YouGile
и обновляет .env на сервере.

Где взять API ключ YouGile:
  1. Войдите на ru.yougile.com
  2. Кликните на аватар (правый верхний угол)
  3. Настройки → API (или: Настройки → Безопасность → API-токены)
  4. Создайте новый токен, скопируйте его сюда

Использование:
  python setup_yougile.py --key YOUR_API_KEY [--deploy]
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from typing import Any


BASE = "https://ru.yougile.com/api-v2"


def api_get(path: str, key: str) -> Any:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return None


def api_post(path: str, key: str, payload: dict) -> Any:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return None


def choose(items: list[dict], name_key: str, id_key: str, prompt: str) -> tuple[str, str]:
    print(f"\n{prompt}:")
    for i, item in enumerate(items):
        print(f"  [{i}] {item[name_key]}  (id: {item[id_key]})")
    while True:
        try:
            idx = int(input("Введите номер: ").strip())
            if 0 <= idx < len(items):
                return items[idx][id_key], items[idx][name_key]
        except (ValueError, KeyboardInterrupt):
            pass
        print("  Неверный выбор, попробуйте ещё раз.")


def main():
    parser = argparse.ArgumentParser(description="YouGile integration setup")
    parser.add_argument("--key", required=True, help="YouGile API key")
    parser.add_argument("--deploy", action="store_true", help="Update .env on server and restart")
    parser.add_argument("--server", default="85.159.231.68", help="Server IP")
    args = parser.parse_args()

    key = args.key.strip()
    print(f"\n=== YouGile Integration Setup ===")
    print(f"API key: {key[:8]}...{key[-4:]}\n")

    # 1. Verify key and get companies
    print("Получаем список компаний...")
    result = api_get("/auth/companies", key)
    if result is None:
        print("❌ Ошибка: API-ключ недействителен или нет доступа.")
        sys.exit(1)

    companies = result if isinstance(result, list) else result.get("content", [])
    if not companies:
        print("❌ Нет доступных компаний. Проверьте API-ключ.")
        sys.exit(1)

    print(f"✅ Доступно компаний: {len(companies)}")

    # 2. Choose company
    company_id, company_name = choose(companies, "name", "id", "Выберите компанию")
    print(f"Выбрана компания: {company_name} ({company_id})")

    # 3. Get projects
    print("\nПолучаем проекты...")
    result = api_get(f"/projects?companyId={company_id}", key)
    projects = result if isinstance(result, list) else (result or {}).get("content", [])
    if not projects:
        print("❌ Нет проектов в этой компании.")
        sys.exit(1)

    project_id, project_name = choose(projects, "title", "id", "Выберите проект")
    print(f"Выбран проект: {project_name} ({project_id})")

    # 4. Get boards
    print("\nПолучаем доски...")
    result = api_get(f"/boards?projectId={project_id}", key)
    boards = result if isinstance(result, list) else (result or {}).get("content", [])
    if not boards:
        print("❌ Нет досок в проекте.")
        sys.exit(1)

    board_id, board_name = choose(boards, "title", "id", "Выберите доску")
    print(f"Выбрана доска: {board_name} ({board_id})")

    # 5. Get columns
    print("\nПолучаем колонки доски...")
    result = api_get(f"/board-columns?boardId={board_id}", key)
    columns = result if isinstance(result, list) else (result or {}).get("content", [])
    if not columns:
        print("❌ Нет колонок на доске.")
        sys.exit(1)

    print("\nКолонки на доске:")
    for col in columns:
        print(f"  - {col.get('title', '?'):<20} id: {col['id']}")

    print("\nНастройте маппинг колонок (нажмите Enter для пропуска):")

    def pick_col(label: str, default_keyword: str) -> str:
        match = next((c for c in columns
                      if default_keyword.lower() in c.get("title", "").lower()), None)
        if match:
            val = input(f"  {label} [{match['title']}]: ").strip()
            return val or match["id"]
        val = input(f"  {label} (id): ").strip()
        return val

    col_backlog     = pick_col("Backlog / Входящие", "backlog")
    col_todo        = pick_col("To Do / Задачи", "to do") or pick_col("To Do / Задачи", "todo")
    col_in_progress = pick_col("In Progress / В работе", "progress")
    col_review      = pick_col("Review / На проверке", "review")
    col_blocked     = pick_col("Blocked / Заблокировано", "block")
    col_done        = pick_col("Done / Готово", "done")

    # 6. Summary
    env_lines = f"""
# YouGile Integration — добавьте в .env на сервере:
BOARD_PROVIDER=yougile
YOUGILE_ENABLED=true
YOUGILE_API_BASE_URL=https://ru.yougile.com
YOUGILE_API_KEY={key}
YOUGILE_COMPANY_ID={company_id}
YOUGILE_PROJECT_ID={project_id}
YOUGILE_BOARD_ID={board_id}
YOUGILE_COLUMN_BACKLOG_ID={col_backlog}
YOUGILE_COLUMN_TODO_ID={col_todo}
YOUGILE_COLUMN_IN_PROGRESS_ID={col_in_progress}
YOUGILE_COLUMN_REVIEW_ID={col_review}
YOUGILE_COLUMN_BLOCKED_ID={col_blocked}
YOUGILE_COLUMN_DONE_ID={col_done}
"""
    print("\n" + "=" * 55)
    print("РЕЗУЛЬТАТ (добавьте в .env):")
    print("=" * 55)
    print(env_lines)

    # Save to local file
    out_path = "yougile_env.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(env_lines.strip())
    print(f"Сохранено в: {out_path}")

    # 7. Deploy to server
    if args.deploy:
        print("\nДеплою на сервер...")
        try:
            import paramiko
        except ImportError:
            print("pip install paramiko — нужен для деплоя")
            return

        import time
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pwd = input(f"SSH пароль для root@{args.server}: ").strip()
        client.connect(args.server, username="root", password=pwd, timeout=15)

        for line in env_lines.strip().splitlines():
            if not line or line.startswith("#"):
                continue
            key_name = line.split("=", 1)[0]
            # Remove old line and add new
            client.exec_command(f"sed -i '/^{key_name}=/d' /opt/grey-cardinal/.env")
            time.sleep(0.1)
            _, _, stderr = client.exec_command(
                f"echo '{line}' >> /opt/grey-cardinal/.env"
            )

        # Restart brain-api
        print("Перезапускаю brain-api...")
        _, stdout, _ = client.exec_command(
            "cd /opt/grey-cardinal && "
            "docker compose -f docker-compose.prod.yml up -d brain-api 2>&1 | tail -3"
        )
        print(stdout.read().decode())
        client.close()
        print("✅ YouGile настроен и задеплоен!")
    else:
        print("\nЧтобы задеплоить на сервер автоматически, запустите:")
        print(f"  python setup_yougile.py --key {key[:8]}... --deploy")


if __name__ == "__main__":
    main()
