"""Grey Cardinal — наполнение продовой БД демонстрационными данными.

Запускается ВНУТРИ контейнера brain-api (Python 3.12, есть все зависимости и
переменные окружения):

    docker exec -i grey-cardinal-brain-api-1 python /tmp/seed_demo.py

Создаёт одну компанию, директора, 6 отделов (по 1 руководителю + 9 сотрудников),
кросс-командные проекты, задачи из разных источников с комментариями, созвоны
с транскриптами, эмоциональные сигналы (разные состояния по отделам) и командных
питомцев (один — прокачанный). В конце печатает отчёт с кредами в stdout.

Идемпотентность: если директор demo уже существует — скрипт прерывается.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from brain_api.application.use_cases import team_pet_service as pet_svc
from brain_api.application.use_cases.cross_team_projects import add_collaboration_event
from brain_api.application.use_cases.team_gamification import grant_team_xp
from brain_api.config import get_settings
from brain_api.infrastructure.auth.jwt import hash_password
from brain_api.infrastructure.db import models as m
from brain_api.infrastructure.db.session import create_engine, create_session_factory

random.seed(2026)

NOW = datetime.now(UTC)
PASSWORD = "Demo2026!"
COMPANY_NAME = "ТехноНова"
COMPANY_TZ = "Europe/Moscow"
EMAIL_DOMAIN = "technova.ru"
DIRECTOR_EMAIL = f"director@{EMAIL_DOMAIN}"

# ── Транслитерация для логинов/почты ──────────────────────────────────────────
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text.lower())


# ── Пул имён ──────────────────────────────────────────────────────────────────
FIRST_M = [
    "Алексей", "Дмитрий", "Иван", "Сергей", "Андрей", "Михаил", "Никита",
    "Павел", "Роман", "Кирилл", "Артём", "Егор", "Максим", "Денис", "Олег",
    "Григорий", "Тимур", "Владислав", "Антон", "Глеб", "Степан", "Фёдор",
]
FIRST_F = [
    "Анна", "Мария", "Екатерина", "Ольга", "Наталья", "Дарья", "Юлия",
    "Алина", "Виктория", "Полина", "Ксения", "Елена", "Татьяна", "Софья",
    "Вероника", "Маргарита", "Кристина", "Валерия", "Ирина", "Алиса",
]
LAST_M = [
    "Воронцов", "Соколов", "Морозов", "Лебедев", "Орлов", "Зайцев", "Кузнецов",
    "Новиков", "Волков", "Беляев", "Громов", "Журавлёв", "Киселёв", "Поляков",
    "Тихонов", "Фомин", "Гордеев", "Савельев", "Карпов", "Лазарев", "Носов",
    "Дроздов", "Ершов", "Сидоров", "Панов", "Якушев", "Минин", "Демидов",
    "Власов", "Котов", "Балашов", "Сафонов", "Рябов", "Шилов", "Уваров",
]
LAST_F = [
    "Воронцова", "Соколова", "Морозова", "Лебедева", "Орлова", "Зайцева",
    "Кузнецова", "Новикова", "Волкова", "Беляева", "Громова", "Журавлёва",
    "Киселёва", "Полякова", "Тихонова", "Фомина", "Гордеева", "Савельева",
    "Карпова", "Лазарева", "Носова", "Дроздова", "Ершова", "Сидорова",
    "Панова", "Якушева", "Минина", "Демидова", "Власова", "Котова",
]

_used_emails: set[str] = set()
_used_names: set[tuple[str, str]] = set()


def gen_person() -> tuple[str, str, str, str]:
    """Вернуть (first, last, email, login) — уникальные."""
    for _ in range(2000):
        if random.random() < 0.5:
            first, last = random.choice(FIRST_M), random.choice(LAST_M)
        else:
            first, last = random.choice(FIRST_F), random.choice(LAST_F)
        if (first, last) in _used_names:
            continue
        base = f"{translit(first)}.{translit(last)}".replace("ё", "e")
        email = f"{base}@{EMAIL_DOMAIN}"
        n = 1
        while email in _used_emails:
            n += 1
            email = f"{base}{n}@{EMAIL_DOMAIN}"
        _used_names.add((first, last))
        _used_emails.add(email)
        login = email.split("@", 1)[0]
        return first, last, email, login
    raise RuntimeError("Не удалось сгенерировать уникальное имя")


# ── Конфигурация отделов ──────────────────────────────────────────────────────
DEPARTMENTS = [
    {
        "slug": "razrabotka", "name": "Разработка",
        "mood_state": "happy",
        "valence": (0.60, 0.85), "stress": (0.05, 0.20),
        "energy": 0.92, "overdue_ratio": 0.05,
        "pet_name": "Байтик", "species": "dragon", "pet_xp": 1280,
        "manager_title": "Руководитель разработки",
        "titles": ["Backend-разработчик", "Frontend-разработчик", "Тимлид",
                   "DevOps-инженер", "Fullstack-разработчик", "Архитектор"],
        "tasks": [
            "Вынести аутентификацию в отдельный сервис",
            "Оптимизировать SQL-запросы в модуле отчётов",
            "Покрыть платёжный модуль интеграционными тестами",
            "Обновить зависимости и закрыть уязвимости",
            "Реализовать вебхуки для внешних интеграций",
            "Настроить кэширование на уровне API",
            "Завести фичефлаги для постепенного раскатывания",
            "Перевести сборку на multi-stage Docker",
            "Добавить трейсинг запросов (OpenTelemetry)",
            "Рефакторинг слоя доступа к данным",
            "Внедрить rate-limiting на публичные эндпоинты",
            "Поднять покрытие тестами до 80%",
            "Мигрировать очередь задач на новый брокер",
            "Описать OpenAPI-спеку для v2 API",
        ],
    },
    {
        "slug": "design", "name": "Дизайн и продукт",
        "mood_state": "content",
        "valence": (0.30, 0.55), "stress": (0.15, 0.30),
        "energy": 0.72, "overdue_ratio": 0.12,
        "pet_name": "Пиксель", "species": "fox", "pet_xp": 520,
        "manager_title": "Арт-директор",
        "titles": ["Продуктовый дизайнер", "UX-исследователь", "UI-дизайнер",
                   "Графический дизайнер", "Motion-дизайнер", "Продакт-менеджер"],
        "tasks": [
            "Обновить дизайн-систему до версии 3.0",
            "Провести юзабилити-тест онбординга",
            "Нарисовать иллюстрации для лендинга",
            "Сделать прототип мобильного дашборда",
            "Редизайн экрана настроек",
            "Подготовить макеты под тёмную тему",
            "Собрать гайдлайн по иконкам",
            "Исследовать путь пользователя при оплате",
            "Анимировать состояние загрузки",
            "Свести воедино токены цветов и типографики",
            "Прототип карточки задачи в Figma",
            "A/B-тест кнопки призыва к действию",
        ],
    },
    {
        "slug": "marketing", "name": "Маркетинг",
        "mood_state": "neutral",
        "valence": (-0.05, 0.20), "stress": (0.30, 0.45),
        "energy": 0.55, "overdue_ratio": 0.20,
        "pet_name": "Хайп", "species": "owl", "pet_xp": 320,
        "manager_title": "Руководитель маркетинга",
        "titles": ["SMM-менеджер", "Контент-маркетолог", "Performance-маркетолог",
                   "PR-менеджер", "Email-маркетолог", "Аналитик трафика"],
        "tasks": [
            "Запустить рекламную кампанию в VK",
            "Подготовить контент-план на квартал",
            "Написать серию писем для прогрева",
            "Проанализировать конверсию воронки",
            "Снять видео-кейс с клиентом",
            "Обновить посадочную под акцию",
            "Согласовать бюджет на таргет",
            "Собрать дайджест новостей отрасли",
            "Настроить сквозную аналитику",
            "Провести вебинар по продукту",
            "Оформить рассылку по базе",
        ],
    },
    {
        "slug": "sales", "name": "Продажи",
        "mood_state": "busy",
        "valence": (0.20, 0.45), "stress": (0.40, 0.60),
        "energy": 0.60, "overdue_ratio": 0.25,
        "pet_name": "Профит", "species": "fox", "pet_xp": 640,
        "manager_title": "Руководитель отдела продаж",
        "titles": ["Менеджер по продажам", "Аккаунт-менеджер", "Sales-менеджер",
                   "Менеджер по работе с ключевыми клиентами", "Пресейл",
                   "Менеджер по развитию"],
        "tasks": [
            "Закрыть сделку с ключевым клиентом",
            "Подготовить КП для корпоративного тарифа",
            "Провести демо для входящего лида",
            "Обновить скрипт холодного звонка",
            "Согласовать договор с юристами",
            "Прозвонить базу реактивации",
            "Завести сделки в CRM за неделю",
            "Подготовить отчёт по плану продаж",
            "Обработать заявки с конференции",
            "Допродажа модуля аналитики текущим клиентам",
            "Назначить встречи с тёплыми лидами",
        ],
    },
    {
        "slug": "qa", "name": "Тестирование (QA)",
        "mood_state": "sad",
        "valence": (-0.70, -0.35), "stress": (0.60, 0.85),
        "energy": 0.34, "overdue_ratio": 0.45,
        "pet_name": "Кьюшка", "species": "capybara", "pet_xp": 180,
        "manager_title": "Руководитель QA",
        "titles": ["QA-инженер", "Автотестировщик", "Мануальный тестировщик",
                   "QA Lead", "Тестировщик нагрузки", "SDET"],
        "tasks": [
            "Регрессионное тестирование релиза 2.4",
            "Завести баги по платёжному модулю",
            "Написать автотесты на критичный флоу",
            "Нагрузочное тестирование API",
            "Проверить сценарии восстановления пароля",
            "Тест-кейсы для новой роли пользователя",
            "Разобрать флаки-тесты в CI",
            "Тестирование на мобильных устройствах",
            "Проверка совместимости браузеров",
            "Воспроизвести баг с потерей сессии",
            "Smoke-тест после деплоя",
            "Актуализировать тест-план",
        ],
    },
    {
        "slug": "support", "name": "Клиентская поддержка",
        "mood_state": "tired",
        "valence": (0.05, 0.30), "stress": (0.35, 0.55),
        "energy": 0.20, "overdue_ratio": 0.30,
        "pet_name": "Хелпи", "species": "capybara", "pet_xp": 410,
        "manager_title": "Руководитель поддержки",
        "titles": ["Специалист поддержки", "Агент 1-й линии", "Агент 2-й линии",
                   "Менеджер по работе с обращениями", "Технический специалист",
                   "Customer Success менеджер"],
        "tasks": [
            "Разобрать очередь обращений за выходные",
            "Обновить базу знаний по типовым вопросам",
            "Эскалировать инцидент с оплатой",
            "Подготовить ответы-шаблоны",
            "Связаться с клиентами по тикетам SLA",
            "Записать инструкцию по настройке интеграции",
            "Обработать жалобы из сторов",
            "Свести отчёт по удовлетворённости (CSAT)",
            "Помочь клиенту с миграцией данных",
            "Закрыть просроченные тикеты",
            "Передать частые баги в разработку",
        ],
    },
]

TASK_SOURCES = [
    ("telegram_chat", "telegram"),
    ("telegram_direct", "telegram"),
    ("meeting_transcript", "meeting"),
    ("manual", "web"),
    ("yougile_import", "yougile"),
    ("daily_sync", "daily_sync"),
]
PRIORITIES = ["low", "medium", "high", "critical"]
ACTIVE_STATUSES = ["todo", "in_progress", "blocked", "review"]

COMMENTS_POOL = [
    "Взял в работу, к концу недели будет готово.",
    "Здесь нужна помощь — заблокирован на стороне смежной команды.",
    "Поправил по замечаниям, отправил на ревью.",
    "提Согласовал с заказчиком, можно продолжать.",
    "Добавил детали в описание, посмотрите.",
    "Сроки сдвигаются на пару дней, предупредил руководителя.",
    "Готово, проверьте пожалуйста.",
    "Договорились обсудить на ближайшем созвоне.",
    "Спасибо, отличная работа! 🔥",
    "Нашёл причину, чиню.",
    "Перенёс в ревью, жду апрув.",
    "Уточните, пожалуйста, ожидаемый результат.",
]
COMMENTS_POOL = [c for c in COMMENTS_POOL if "提" not in c]

TRANSCRIPT_POOL = [
    "Коллеги, давайте быстро пройдёмся по статусам.",
    "У меня по задаче всё идёт по плану, без блокеров.",
    "Есть риск по срокам, нужна помощь от смежников.",
    "Предлагаю вынести это в отдельную задачу.",
    "Хорошо, тогда я беру это на себя.",
    "Зафиксируем как решение и идём дальше.",
    "По метрикам видим рост, продолжаем в том же духе.",
    "Давайте синхронизируемся ещё раз в четверг.",
]


async def main() -> None:
    dry = os.getenv("GC_SEED_DRY_RUN") == "1"
    settings = get_settings()
    engine = create_engine(settings.database_url, echo=False)
    Session = create_session_factory(engine)

    report: dict = {"company": COMPANY_NAME, "password_all": PASSWORD, "departments": []}

    async with Session() as session:
        # Idempotency guard.
        existing = await session.scalar(
            select(m.UserModel).where(m.UserModel.email == DIRECTOR_EMAIL)
        )
        if existing is not None:
            print("ALREADY_SEEDED: director already exists, aborting.", file=sys.stderr)
            await engine.dispose()
            return

        # Global meeting seq base.
        meeting_seq = int(await session.scalar(select(func.max(m.MeetingModel.seq))) or 0)

        # ── Director + company ────────────────────────────────────────────────
        director = m.UserModel(
            id=uuid4(), email=DIRECTOR_EMAIL, login="director",
            password_hash=hash_password(PASSWORD),
            first_name="Алексей", last_name="Воронцов",
            display_name="Алексей Воронцов",
            bio="Генеральный директор ТехноНова", photo_data_url="",
            role="Генеральный директор", timezone=COMPANY_TZ,
        )
        session.add(director)
        await session.flush()
        _used_emails.add(DIRECTOR_EMAIL)
        _used_names.add(("Алексей", "Воронцов"))

        company = m.CompanyModel(
            id=uuid4(), name=COMPANY_NAME, timezone=COMPANY_TZ, created_by=director.id
        )
        session.add(company)
        await session.flush()
        session.add(m.CompanyAdminModel(
            id=uuid4(), company_id=company.id, user_id=director.id, role="director"
        ))
        await session.flush()

        report["director"] = {"email": DIRECTOR_EMAIL, "password": PASSWORD,
                              "name": "Алексей Воронцов"}
        report["company_id"] = str(company.id)

        teams_ctx: list[dict] = []

        # ── Departments ───────────────────────────────────────────────────────
        for dep in DEPARTMENTS:
            emo_cfg = {
                "emotion_analysis": {"enabled": True, "sources": {"chat_text": True}},
                "digest_mode": "morning",
                "meeting_reminders": True,
            }
            team = m.TeamModel(
                id=uuid4(), company_id=company.id, name=dep["name"],
                timezone=COMPANY_TZ, board_provider="mock", board_config=emo_cfg,
            )
            session.add(team)
            await session.flush()

            # Manager.
            mf, ml, memail, mlogin = gen_person()
            manager = m.UserModel(
                id=uuid4(), email=memail, login=mlogin,
                password_hash=hash_password(PASSWORD),
                first_name=mf, last_name=ml, display_name=f"{mf} {ml}",
                bio=dep["manager_title"], photo_data_url="",
                role=dep["manager_title"], timezone=COMPANY_TZ,
            )
            session.add(manager)
            await session.flush()
            session.add(m.TeamMemberModel(
                id=uuid4(), team_id=team.id, user_id=manager.id,
                role="manager", invited_by=director.id,
            ))

            employees: list[m.UserModel] = []
            emp_report = []
            for _ in range(9):
                ef, el, eemail, elogin = gen_person()
                title = random.choice(dep["titles"])
                emp = m.UserModel(
                    id=uuid4(), email=eemail, login=elogin,
                    password_hash=hash_password(PASSWORD),
                    first_name=ef, last_name=el, display_name=f"{ef} {el}",
                    bio=title, photo_data_url="", role=title, timezone=COMPANY_TZ,
                )
                session.add(emp)
                await session.flush()
                session.add(m.TeamMemberModel(
                    id=uuid4(), team_id=team.id, user_id=emp.id,
                    role="employee", invited_by=manager.id,
                ))
                employees.append(emp)
                emp_report.append({"name": f"{ef} {el}", "email": eemail, "title": title})
            await session.flush()

            all_members = [manager] + employees

            # Pet (создаёт стартовый инвентарь + privacy).
            pet = await pet_svc.create_pet(
                session, team.id, name=dep["pet_name"], species=dep["species"], now=NOW
            )
            # Включить анализ задач и чата (privacy) для демонстрации эмоций.
            await pet_svc.update_privacy(
                session, team.id,
                {"analyze_tasks": True, "analyze_chat": True,
                 "manager_individual_signals": True, "team_aggregates_only": False},
                can_enable_sensitive=True,
            )

            # ── Tasks ─────────────────────────────────────────────────────────
            seq = 0
            done_count = 0
            task_titles = dep["tasks"]
            for i, title in enumerate(task_titles):
                seq += 1
                src, src_type = random.choice(TASK_SOURCES)
                assignee = random.choice(employees)
                # Распределение статусов.
                roll = random.random()
                overdue = random.random() < dep["overdue_ratio"]
                if roll < 0.42:
                    status = "done"
                elif roll < 0.62:
                    status = "in_progress"
                elif roll < 0.74:
                    status = "todo"
                elif roll < 0.84:
                    status = "review"
                elif roll < 0.92:
                    status = "blocked"
                else:
                    status = "cancelled"

                created_at = NOW - timedelta(days=random.randint(2, 20),
                                             hours=random.randint(0, 23))
                completed_at = None
                deadline = None
                if status == "done":
                    completed_at = NOW - timedelta(days=random.randint(0, 3),
                                                   hours=random.randint(0, 23))
                    deadline = completed_at + timedelta(days=random.randint(-1, 3))
                    done_count += 1
                elif status != "cancelled":
                    if overdue:
                        deadline = NOW - timedelta(days=random.randint(1, 5))
                    else:
                        deadline = NOW + timedelta(days=random.randint(1, 12))

                src_url = None
                source_text = None
                if src == "yougile_import":
                    src_url = f"https://ru.yougile.com/team/board/{uuid4().hex[:12]}"
                if src in ("telegram_chat", "telegram_direct"):
                    source_text = f"{assignee.display_name}, нужно: {title.lower()}"
                if src == "meeting_transcript":
                    source_text = f"На созвоне договорились: {title.lower()}"

                task = m.TaskModel(
                    id=uuid4(), seq=seq, public_id=f"GC-{seq}",
                    team_id=team.id, title=title,
                    description=f"{title}. Отдел: {dep['name']}.",
                    status=status, priority=random.choice(PRIORITIES),
                    assignee_id=assignee.id, assignee_text=assignee.display_name,
                    deadline=deadline, deadline_timezone=COMPANY_TZ,
                    source=src, source_type=src_type, source_text=source_text,
                    source_url=src_url, created_at=created_at,
                    completed_at=completed_at,
                    last_status_update_at=completed_at or created_at,
                )
                session.add(task)
                await session.flush()

                # Комментарии (~45% задач).
                if random.random() < 0.45:
                    for _ in range(random.randint(1, 3)):
                        author = random.choice(all_members)
                        session.add(m.TaskCommentModel(
                            id=uuid4(), task_id=task.id, author_id=author.id,
                            author_name=author.display_name,
                            body=random.choice(COMMENTS_POOL),
                        ))

                # XP за выполненные задачи (кормит питомца + лидерборд).
                if status == "done":
                    await grant_team_xp(
                        session, user_id=assignee.id, team_id=team.id,
                        kind="task_completed", points=20,
                        reason=f"Закрыл задачу {task.public_id}",
                        idempotency_key=f"seed_task_done:{task.id}",
                        task_id=task.id,
                    )
                elif status in ("in_progress", "review"):
                    await grant_team_xp(
                        session, user_id=assignee.id, team_id=team.id,
                        kind="status_updated", points=3,
                        reason=f"Обновил статус {task.public_id}",
                        idempotency_key=f"seed_task_status:{task.id}",
                        task_id=task.id,
                    )
            await session.flush()

            # ── Emotion signals (разное состояние по отделам) ─────────────────
            vmin, vmax = dep["valence"]
            smin, smax = dep["stress"]
            for _ in range(random.randint(10, 16)):
                u = random.choice(all_members)
                session.add(m.EmotionSignalModel(
                    id=uuid4(), team_id=team.id, user_id=u.id,
                    source=random.choice(["chat_text", "behavior", "call_audio"]),
                    valence=round(random.uniform(vmin, vmax), 3),
                    arousal=round(random.uniform(0.3, 0.8), 3),
                    stress=round(random.uniform(smin, smax), 3),
                    confidence=round(random.uniform(0.55, 0.9), 3),
                    source_ref={"demo": True},
                    created_at=NOW - timedelta(days=random.randint(0, 6),
                                               hours=random.randint(0, 23)),
                ))
            await session.flush()

            # ── Meetings / созвоны ────────────────────────────────────────────
            # 1) Прошедший завершённый созвон с транскриптом и саммари.
            meeting_seq += 1
            past_start = NOW - timedelta(days=random.randint(2, 6),
                                         hours=random.randint(1, 6))
            past = m.MeetingModel(
                id=uuid4(), seq=meeting_seq, public_id=f"MTG-{meeting_seq}",
                team_id=team.id, external_source="yandex_telemost",
                title=f"Еженедельный синк — {dep['name']}",
                status="stopped", state="finished", created_by=manager.id,
                created_by_user_id=manager.id,
                scheduled_at=past_start, scheduled_timezone=COMPANY_TZ,
                duration_minutes=30, started_at=past_start,
                stopped_at=past_start + timedelta(minutes=32),
                summary=(f"Команда «{dep['name']}» прошлась по статусам. "
                         "Зафиксированы 2 решения и 1 риск по срокам. "
                         "Договорились о повторной синхронизации."),
            )
            session.add(past)
            await session.flush()
            present = random.sample(all_members, k=min(6, len(all_members)))
            for idx, u in enumerate(present):
                session.add(m.MeetingParticipantModel(
                    id=uuid4(), meeting_id=past.id, user_id=u.id,
                    status="left", joined_at=past_start,
                    left_at=past_start + timedelta(minutes=32),
                    last_seen_at=past_start + timedelta(minutes=32),
                ))
                session.add(m.MeetingRsvpModel(
                    id=uuid4(), meeting_id=past.id, user_id=u.id, status="yes"
                ))
                # Транскрипт-реплики.
                line = m.TranscriptEventModel(
                    id=uuid4(), meeting_db_id=past.id, meeting_id=past.public_id,
                    speaker_id=str(u.id), speaker_name=u.display_name,
                    text=random.choice(TRANSCRIPT_POOL),
                    ts=past_start + timedelta(minutes=idx * 3 + 1),
                    is_final=True, confidence=0.92, source="asr",
                )
                session.add(line)
                # XP за участие в созвоне.
                await grant_team_xp(
                    session, user_id=u.id, team_id=team.id,
                    kind="meeting_joined", points=5,
                    reason=f"Участвовал в созвоне {past.public_id}",
                    idempotency_key=f"seed_meeting_join:{past.id}:{u.id}",
                    meeting_id=past.id,
                )
            # Саммари-XP руководителю.
            await grant_team_xp(
                session, user_id=manager.id, team_id=team.id,
                kind="meeting_summary_ready", points=5,
                reason=f"Получено саммари {past.public_id}",
                idempotency_key=f"seed_meeting_summary:{past.id}",
                meeting_id=past.id,
            )

            # 2) Запланированный будущий созвон.
            meeting_seq += 1
            fut_start = NOW + timedelta(days=random.randint(1, 4),
                                        hours=random.randint(0, 8))
            future = m.MeetingModel(
                id=uuid4(), seq=meeting_seq, public_id=f"MTG-{meeting_seq}",
                team_id=team.id, external_source="telegram",
                title=f"Планирование спринта — {dep['name']}",
                status="scheduled", state="scheduled", created_by=manager.id,
                created_by_user_id=manager.id,
                scheduled_at=fut_start, scheduled_timezone=COMPANY_TZ,
                duration_minutes=60, started_at=fut_start,
            )
            session.add(future)
            await session.flush()
            for u in random.sample(all_members, k=min(7, len(all_members))):
                session.add(m.MeetingRsvpModel(
                    id=uuid4(), meeting_id=future.id, user_id=u.id,
                    status=random.choice(["yes", "yes", "maybe", "no"]),
                ))
            await session.flush()

            # ── Прокачка питомца ──────────────────────────────────────────────
            pet.xp = dep["pet_xp"]
            pet.energy = dep["energy"]
            pet.last_decay_at = NOW
            pet.last_fed_at = NOW
            await session.flush()

            # Для прокачанного отдела — экипировать косметику.
            if dep["slug"] == "razrabotka":
                for item_id in ["sprint_crown", "vr_visor", "focus_flow",
                                "night_city", "battle_ready"]:
                    await pet_svc.grant_item(session, team.id, item_id,
                                             status="owned", reason="demo", now=NOW)
                    await pet_svc.equip_item(session, team.id, item_id, now=NOW)
                await session.flush()

            teams_ctx.append({
                "dep": dep, "team": team, "manager": manager,
                "employees": employees,
            })
            report["departments"].append({
                "name": dep["name"], "team_id": str(team.id),
                "mood": dep["mood_state"],
                "pet": {"name": dep["pet_name"], "species": dep["species"],
                        "level": dep["pet_xp"] // 100 + 1, "xp": dep["pet_xp"]},
                "manager": {"name": manager.display_name, "email": manager.email,
                            "title": dep["manager_title"]},
                "employees": emp_report,
                "tasks_total": len(task_titles), "tasks_done": done_count,
            })

        await session.flush()

        # ── Cross-team projects ───────────────────────────────────────────────
        by_slug = {ctx["dep"]["slug"]: ctx for ctx in teams_ctx}
        project_specs = [
            {
                "name": "Запуск мобильного приложения 2.0",
                "lead": "razrabotka", "teams": ["razrabotka", "design", "qa"],
                "status": "active",
                "desc": "Кросс-командный запуск мобильного приложения нового поколения.",
                "tasks": [
                    ("razrabotka", "Сверстать экраны под новый API", "in_progress"),
                    ("design", "Финальные макеты мобильных экранов", "done"),
                    ("qa", "Тест-план для мобильного релиза", "todo"),
                    ("razrabotka", "Интеграция пуш-уведомлений", "todo"),
                    ("qa", "Регрессия перед публикацией в стор", "blocked"),
                ],
            },
            {
                "name": "Рекламная кампания Q3",
                "lead": "marketing", "teams": ["marketing", "design", "sales"],
                "status": "active",
                "desc": "Совместная рекламная кампания на третий квартал.",
                "tasks": [
                    ("marketing", "Медиаплан и бюджет кампании", "done"),
                    ("design", "Креативы для соцсетей", "in_progress"),
                    ("sales", "Скрипты обработки лидов из кампании", "todo"),
                    ("marketing", "Настройка сквозной аналитики", "review"),
                ],
            },
            {
                "name": "Программа удержания клиентов",
                "lead": "support", "teams": ["support", "sales", "razrabotka"],
                "status": "paused",
                "desc": "Снижение оттока за счёт проактивной поддержки и допродаж.",
                "tasks": [
                    ("support", "Сегментация клиентов по риску оттока", "in_progress"),
                    ("sales", "Сценарии допродаж для текущих клиентов", "todo"),
                    ("razrabotka", "Дашборд здоровья клиента", "todo"),
                ],
            },
            {
                "name": "Внутренняя платформа аналитики",
                "lead": "razrabotka", "teams": ["razrabotka", "qa"],
                "status": "completed",
                "desc": "Единая платформа продуктовой аналитики для всех отделов.",
                "tasks": [
                    ("razrabotka", "ETL-пайплайн событий", "done"),
                    ("qa", "Проверка корректности метрик", "done"),
                    ("razrabotka", "Витрины данных и дашборды", "done"),
                ],
            },
        ]

        project_report = []
        for spec in project_specs:
            lead_ctx = by_slug[spec["lead"]]
            team_ctxs = [by_slug[s] for s in spec["teams"]]
            project = m.CompanyProjectModel(
                id=uuid4(), company_id=company.id,
                code=f"PRJ-{uuid4().hex[:6].upper()}",
                name=spec["name"], description=spec["desc"],
                expected_result=f"Достигнут результат: {spec['name']}.",
                status=spec["status"], owner_id=lead_ctx["manager"].id,
                created_by=director.id,
                starts_at=NOW - timedelta(days=random.randint(10, 30)),
                deadline=NOW + timedelta(days=random.randint(10, 45)),
                budget_min=300000, budget_max=900000,
                source="planner", sync_status="local_only",
            )
            session.add(project)
            await session.flush()

            for ctx in team_ctxs:
                session.add(m.ProjectTeamModel(
                    id=uuid4(), project_id=project.id, team_id=ctx["team"].id,
                    role="lead" if ctx is lead_ctx else "contributor",
                    allocation_percent=100 if ctx is lead_ctx else random.randint(40, 80),
                    participation_status="active",
                ))
                # Менеджер + 3 сотрудника от команды в участники проекта.
                members = [ctx["manager"]] + random.sample(ctx["employees"], 3)
                for u in members:
                    role = "manager" if u is ctx["manager"] else "contributor"
                    if u is lead_ctx["manager"]:
                        role = "owner"
                    session.add(m.ProjectMemberModel(
                        id=uuid4(), project_id=project.id, user_id=u.id,
                        team_id=ctx["team"].id, role=role,
                        allocation_percent=100, active=True,
                    ))
            # Директор — владелец проекта.
            session.add(m.ProjectMemberModel(
                id=uuid4(), project_id=project.id, user_id=director.id,
                team_id=None, role="owner", allocation_percent=0, active=True,
            ))
            await session.flush()

            # Кросс-командные задачи.
            for owner_slug, title, status in spec["tasks"]:
                owner_ctx = by_slug[owner_slug]
                seq, public_id = await _next_seq(session, owner_ctx["team"].id)
                assignee = random.choice(owner_ctx["employees"])
                completed_at = NOW - timedelta(days=random.randint(0, 5)) if status == "done" else None
                task = m.TaskModel(
                    id=uuid4(), seq=seq, public_id=public_id,
                    company_project_id=project.id, team_id=owner_ctx["team"].id,
                    title=title, description=f"{title} (проект «{spec['name']}»).",
                    status=status, priority=random.choice(PRIORITIES),
                    assignee_id=assignee.id, assignee_text=assignee.display_name,
                    deadline=NOW + timedelta(days=random.randint(3, 20)),
                    deadline_timezone=COMPANY_TZ,
                    source="project_planner", source_type="planner",
                    completed_at=completed_at,
                )
                session.add(task)
                await session.flush()
                # Все команды проекта участвуют в задаче (для team map / синергии).
                for ctx in team_ctxs:
                    session.add(m.TaskTeamModel(
                        id=uuid4(), task_id=task.id, team_id=ctx["team"].id,
                        role="owner" if ctx is owner_ctx else "contributor",
                    ))
                session.add(m.TaskAssigneeModel(
                    id=uuid4(), task_id=task.id, user_id=assignee.id, role="owner",
                ))
                if status == "done":
                    await grant_team_xp(
                        session, user_id=assignee.id, team_id=owner_ctx["team"].id,
                        kind="cross_team_task_completed", points=15,
                        reason=f"Закрыл межкомандную задачу {public_id}",
                        idempotency_key=f"seed_cross_done:{task.id}",
                        task_id=task.id,
                    )
                    for ctx in team_ctxs:
                        if ctx is owner_ctx:
                            continue
                        await add_collaboration_event(
                            session, company_id=company.id, project_id=project.id,
                            task_id=task.id, actor_user_id=assignee.id,
                            source_team_id=owner_ctx["team"].id,
                            target_team_id=ctx["team"].id,
                            kind="cross_team_task_completed", points=15,
                            idempotency_key=f"seed_cross_evt:{task.id}:{ctx['team'].id}",
                        )

            # project_started события (синергия команд на карте).
            for ctx in team_ctxs:
                if ctx is lead_ctx:
                    continue
                await add_collaboration_event(
                    session, company_id=company.id, project_id=project.id,
                    kind="project_started", source_team_id=lead_ctx["team"].id,
                    target_team_id=ctx["team"].id, actor_user_id=director.id,
                    points=5,
                    idempotency_key=f"seed_proj_start:{project.id}:{ctx['team'].id}",
                )

            project_report.append({
                "name": spec["name"], "code": project.code, "status": spec["status"],
                "lead": lead_ctx["dep"]["name"],
                "teams": [by_slug[s]["dep"]["name"] for s in spec["teams"]],
                "tasks": len(spec["tasks"]),
            })

        if dry:
            await session.rollback()
        else:
            await session.commit()

    report["projects"] = project_report
    print("=" * 70)
    print("SEED_DRYRUN_OK" if dry else "SEED_OK")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    await engine.dispose()


async def _next_seq(session, team_id):
    cur = await session.scalar(
        select(func.max(m.TaskModel.seq)).where(m.TaskModel.team_id == team_id)
    )
    seq = int(cur or 0) + 1
    return seq, f"GC-{seq}"


if __name__ == "__main__":
    asyncio.run(main())
