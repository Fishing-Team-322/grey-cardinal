# Дизайн: Расчёт нового проекта (Project Estimation)

> Статус: **дизайн** (Bucket B). Кода пока нет — этот документ описывает,
> как фича ляжет на существующую архитектуру Grey Cardinal.

## Зачем

Руководитель/директор хочет до старта проекта получить оценку:
**риски, бюджет, сроки, по квалификации сотрудников и хватает ли текущего
штата** или нужно нанимать. Сейчас система знает задачи/исполнителей/историю,
но не умеет «прикинуть проект» целиком.

## Входные данные (что уже есть в системе)

| Источник | Таблица | Что даёт |
|---|---|---|
| Описание проекта | вход от пользователя | scope, цели, ограничения |
| Ростер команды | `team_members` + `users` | кто есть, роли (manager/employee) |
| История задач | `tasks` (status, deadline, completed_at, assignee_id) | фактическая скорость, типы работ |
| Доска | `board_cards`, YouGile | связь с реальными карточками |
| Геймификация | `user_xp_events`, `user_xp_totals` | прокси-сигнал «опытности» исполнителя |
| Отчёты по сотруднику | `member_reports.member_report_payload` | on_time_rate, avg_completion_hours |

`member_report_payload` (apps/brain-api/.../use_cases/member_reports.py) уже
считает on-time rate и среднее время выполнения — это готовый сигнал
производительности на сотрудника.

## Пайплайн

```
Описание проекта (текст / голос)
  → LLM-декомпозиция в work items (роль, оценка часов, зависимости, риск-флаги)
  → Сметная калькуляция (часы × ставка роли → бюджет; критический путь → срок)
  → Риск-реестр (LLM + эвристики: незакрытые зависимости, новые технологии,
     перегрузка ключевых людей)
  → Капасити-чек: суммарные часы по ролям vs доступность штата
     (на основе истории скорости и текущей загрузки активными задачами)
  → Итог: бюджет (диапазон), срок (P50/P90), нехватка ролей, рекомендации
```

LLM вызывается через существующий `SemanticMessageParser` стек
(`LLMProviderFactory.resolve_for_team`) — те же провайдеры (Groq→OpenRouter→
Ollama), та же strict-JSON валидация через Pydantic-схему.

## Модель данных (новые таблицы)

```python
class ProjectEstimateModel:          # одна оценка проекта
    id, team_id, title, description
    status            # draft | computed | approved | archived
    currency, total_cost_min, total_cost_max
    duration_days_p50, duration_days_p90
    capacity_verdict  # 'fits' | 'hire_needed' | 'tight'
    summary_payload(JSON)  # человекочитаемый разбор + рекомендации
    created_by, created_at

class EstimateLineItemModel:          # work item
    id, estimate_id, title, role
    hours_min, hours_max, depends_on(JSON list)
    suggested_assignee_id(nullable)   # из текущего штата, если подходит

class EstimateRiskModel:
    id, estimate_id, kind             # tech | capacity | dependency | external
    severity                          # low | medium | high
    description, mitigation
```

Миграция в стиле существующих (`0015_*` как образец; `sa.JSON()` для payload,
`sa.Uuid()` для ключей).

## Капасити-чек (как считаем «хватает ли штата»)

1. Сгруппировать `EstimateLineItem.hours` по `role`.
2. Для каждой роли в команде взять «реальную пропускную способность»:
   из истории (`tasks.completed_at - created_at`, `member_report.avg_completion_hours`)
   вывести часов/неделю с поправкой на текущую загрузку (открытые задачи).
3. Сравнить требуемые часы с доступными в горизонте срока →
   `fits` / `tight` / `hire_needed` + конкретно каких ролей не хватает.
4. Квалификация: сопоставить тип work item с прошлым опытом исполнителя
   (теги задач/история) + уровень геймификации как мягкий прокси.

## Точки входа

- **Web-кабинет**: новый раздел «Оценка проекта» (форма scope → результат с
  таблицей line items, рисками, вердиктом по штату). Контракты — в стиле
  `grey_board`/`v2_tenants` роутов.
- **Бот**: команда `/estimate <описание>` или свободный текст с интентом
  «прикинь проект» → ссылка на страницу с расчётом (паттерн `create_share_link`
  из `meeting_summary`, как уже сделано для дайджеста/саммари).

## Приватность/доступ

Доступ к расчёту — только manager/director команды (переиспользовать
`_actor_can_manage` из internal_telegram / паттерн `manager_report_*`).

## Этапы реализации

1. Модели + миграция + LLM-промпт декомпозиции (strict JSON схема).
2. Калькулятор бюджета/срока + капасити-чек на исторических данных.
3. Риск-реестр (эвристики + LLM).
4. Web-страница результата + share-link из бота.
5. Тесты: декомпозиция (фейковый LLM), капасити на сид-данных, доступ по ролям.
