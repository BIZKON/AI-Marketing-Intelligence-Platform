# МАСТЕР-ОТЧЁТ: Аудит AI Marketing Intelligence Platform

**Дата:** 2026-02-06
**Метод:** Параллельный аудит 6 специализированных агентов
**Охват:** Backend, Frontend, Telegram Bot, Security, Architecture, Data Models, Tests, CI/CD, Docker

---

## СОДЕРЖАНИЕ

1. [Сводка](#1-сводка)
2. [Критические точки слома](#2-критические-точки-слома)
3. [Отчёт Агента 1 — Backend Code Bugs](#3-агент-1--backend-code-bugs)
4. [Отчёт Агента 2 — Security Vulnerabilities](#4-агент-2--security-vulnerabilities)
5. [Отчёт Агента 3 — Frontend & Bot & Tests](#5-агент-3--frontend--bot--tests)
6. [Отчёт Агента 4 — Architecture & Business Logic](#6-агент-4--architecture--business-logic)
7. [Отчёт Агента 6 — Data Models & Schemas](#7-агент-6--data-models--schemas)
8. [Дедуплицированный реестр всех проблем](#8-дедуплицированный-реестр-всех-проблем)
9. [План изменений](#9-план-изменений)

---

## 1. СВОДКА

| Метрика | Значение |
|---------|----------|
| Файлов проверено | 75+ |
| Строк кода | ~7,000+ |
| Уникальных проблем найдено | **87** (после дедупликации) |
| CRITICAL | **11** |
| HIGH | **23** |
| MEDIUM | **38** |
| LOW | **15** |
| Агентов задействовано | 6 |

### Распределение по области

| Область | CRIT | HIGH | MED | LOW | Всего |
|---------|------|------|-----|-----|-------|
| Backend (код, логика) | 2 | 7 | 5 | 3 | 17 |
| Security | 2 | 5 | 6 | 3 | 16 |
| Architecture & Logic | 3 | 7 | 9 | 3 | 22 |
| Data Models & Schemas | 4 | 7 | 8 | 4 | 23 |
| Frontend | 0 | 2 | 4 | 2 | 8 |
| Telegram Bot | 1 | 3 | 7 | 6 | 17 |
| Tests & CI/CD | 1 | 3 | 6 | 2 | 12 |

---

## 2. КРИТИЧЕСКИЕ ТОЧКИ СЛОМА

> Эти 11 проблем представляют собой **точки, при которых система ломается или становится уязвимой**. Без их устранения проект нельзя выводить в продакшн.

### BREAK-01: Обход аутентификации Telegram (полный bypass)
- **Файл:** `backend/app/services/user_service.py:80`
- **Суть:** Верификация HMAC-хеша Telegram Login Widget выполняется условно — если `hash_value`, `auth_date` или `bot_token` не переданы, проверка полностью пропускается. Атакующий отправляет `{"telegram_id": <любой_id>}` без `hash` и получает валидный JWT.
- **Импакт:** Любой может получить доступ к любому аккаунту Telegram-пользователя. Это **полный authentication bypass**.

### BREAK-02: Дефолтный JWT Secret Key в исходном коде
- **Файл:** `backend/app/core/config.py:18`
- **Суть:** `secret_key = "change-me-in-production"`. Если `.env` не настроен, токены подписываются этим значением. Любой, кто видел исходный код, может подделать JWT.
- **Импакт:** Полная подделка JWT-токенов, доступ к любому аккаунту.

### BREAK-03: `scalar_first()` не существует — admin endpoint сломан
- **Файл:** `backend/app/api/routers/admin.py:226`
- **Суть:** Вызывается `result.scalar_first()`, но такого метода в SQLAlchemy нет. Нужно `.scalars().first()`.
- **Импакт:** Endpoint `PATCH /admin/users/{id}/plan` падает с `AttributeError` при каждом вызове.

### BREAK-04: Месячный лимит задач считает ВСЕ задачи, а не за текущий месяц
- **Файл:** `backend/app/api/routers/content.py:162-165`
- **Суть:** Запрос `count()` не фильтрует по `created_at >= month_start`. После создания N задач за всё время пользователь навсегда заблокирован.
- **Импакт:** Платящие пользователи Creator/Autopilot перманентно теряют возможность создавать контент.

### BREAK-05: Celery-таски передают строку вместо UUID
- **Файл:** `backend/app/workers/tasks.py:211`
- **Суть:** `user_id: str` передаётся в `db.get(User, user_id)`, но `User.id` — UUID. asyncpg не делает неявное приведение типов.
- **Импакт:** Задача `generate_content_plan` падает с type error при каждом запуске.

### BREAK-06: Celery-таски используют строки вместо Enum
- **Файл:** `backend/app/workers/tasks.py:239,278,295`
- **Суть:** `status="pending"`, `status == "approved"`, `status = "published"` — raw strings вместо `TaskStatus.PENDING`, `TaskStatus.APPROVED`, `TaskStatus.PUBLISHED`.
- **Импакт:** Scheduled auto-publishing и генерация контент-планов некорректно работают с PostgreSQL native enums.

### BREAK-07: Конфликт каскадов ContentPlan ↔ ContentTask
- **Файл:** `backend/app/models/content_plan.py:54`, `content_task.py:38`
- **Суть:** ORM cascade `"all, delete-orphan"` удаляет связанные задачи. FK `ondelete="SET NULL"` ставит NULL. Поведение зависит от пути удаления (ORM vs SQL).
- **Импакт:** Непредсказуемое поведение при удалении контент-планов: либо потеря данных, либо orphan записи.

### BREAK-08: Нулевое количество миграций Alembic
- **Файл:** `backend/alembic/versions/.gitkeep`
- **Суть:** Директория `versions/` пуста. Ни одной миграции для 8 таблиц. Нет способа развернуть или эволюционировать схему БД.
- **Импакт:** Невозможен деплой: таблицы нельзя создать через миграции. Нет version control для схемы.

### BREAK-09: Автокоммит в `get_db()` + явные коммиты в routes = двойной коммит
- **Файл:** `backend/app/core/database.py:27-28`, `reports.py:77,112,149,189`
- **Суть:** `get_db()` автоматически коммитит по завершении запроса. Роуты тоже вызывают `await db.commit()`. Между первым и вторым коммитом данные уже зафиксированы, rollback невозможен.
- **Импакт:** Частично закоммиченные данные при ошибках между коммитами. Непредсказуемые транзакции.

### BREAK-10: Webhook Stripe без идемпотентности — дублирование подписок
- **Файл:** `backend/app/services/billing_service.py:119-145`
- **Суть:** При ретрае webhook от Stripe нет проверки на существующую подписку. Создаётся дубликат. Unique constraint вызывает IntegrityError, или `scalar_one_or_none()` ломается при множественных active подписках.
- **Импакт:** Пользователь блокируется из API: dependency `get_active_subscription` выбрасывает исключение при >1 активной подписке.

### BREAK-11: Лимиты voice/video никогда не проверяются
- **Файл:** `backend/app/api/routers/reports.py:124-198`
- **Суть:** Endpoints `request_voice_report` и `request_video_report` никогда не вызывают `LimitsService.check_voice_limit()` / `check_video_limit()`. Еженедельные квоты из `PLAN_LIMITS` не применяются.
- **Импакт:** Любой Creator может генерировать неограниченное количество voice-отчётов. Это прямой cost liability (ElevenLabs, HeyGen API).

---

## 3. АГЕНТ 1 — Backend Code Bugs

**Найдено: 17 проблем (2 CRITICAL, 7 HIGH, 5 MEDIUM, 3 LOW)**

| # | Sev | Файл:Строка | Проблема |
|---|-----|-------------|----------|
| 1 | CRIT | `admin.py:226` | `scalar_first()` не существует — AttributeError |
| 2 | CRIT | `content.py:162-165` | Лимит задач считает all-time вместо monthly |
| 3 | HIGH | `dependencies.py:32` | Необработанный ValueError при невалидном UUID в JWT |
| 4 | HIGH | `report_generator.py:289-296` | `LIMIT` на агрегатном запросе — бессмысленный, avg считает все посты |
| 5 | HIGH | `billing_service.py:70,107,113,131` | Синхронные Stripe вызовы блокируют async event loop |
| 6 | HIGH | `tasks.py:211` | String вместо UUID в `db.get(User, user_id)` |
| 7 | HIGH | `tasks.py:239,278,295` | String literals вместо Enum значений |
| 8 | HIGH | `content.py:430` | Naive vs aware datetime → TypeError |
| 9 | HIGH | `billing.py:65,84,100` | `stripe.error` модуль удалён в stripe v6+ |
| 10 | MED | `reports.py:77,112,149,189` | Double-commit pattern |
| 11 | MED | `redis.py` + `main.py` | Redis connection никогда не закрывается |
| 12 | MED | `report_generator.py:57-62` | String vs UUID type mismatch в competitor ID filter |
| 13 | MED | `tasks.py:222` | Raw strings для enum колонок ContentPlan |
| 14 | MED | `rate_limit.py:32-42` | In-memory rate limiter бесполезен с несколькими workers |
| 15 | MED | `health.py:36-41` | Health check создаёт сессию вне lifecycle |
| 16 | LOW | `publisher.py`, `base.py`, parsers | `os.getenv` вместо централизованного Settings |
| 17 | LOW | `main.py:35` | CORS hardcoded на localhost:3000 |

---

## 4. АГЕНТ 2 — Security Vulnerabilities

**Найдено: 17 уязвимостей (2 CRITICAL, 5 HIGH, 6 MEDIUM, 3 LOW)**

| # | Sev | OWASP | Файл | Уязвимость |
|---|-----|-------|------|------------|
| 1 | CRIT | A07 | `user_service.py:80` | Telegram auth bypass — hash verification optional |
| 2 | CRIT | A02 | `config.py:18` | Дефолтный JWT secret `"change-me-in-production"` |
| 3 | HIGH | A07 | `auth.py:14` | Нет валидации сложности пароля |
| 4 | HIGH | A05 | `rate_limit.py:57-59` | X-Forwarded-For spoofing обходит rate limit |
| 5 | HIGH | A07 | `security.py:13` | JWT 24-часовой lifetime без refresh/revocation |
| 6 | HIGH | A05 | `Dockerfile.*` | Все контейнеры работают как root |
| 7 | HIGH | A05 | (root) | Отсутствует `.dockerignore` — secrets в images |
| 8 | MED | A05 | `docker-compose.yml:26` | Redis без аутентификации, exposed port |
| 9 | MED | A05 | `docker-compose.yml:9-11` | Hardcoded DB credentials `platform:platform` |
| 10 | MED | A05 | `main.py:33-39` | CORS не настраивается через env vars |
| 11 | MED | A01 | `billing.py:43` | Stripe subscription ID leaks to client |
| 12 | MED | A07 | `bot/middlewares/auth.py:23` | Bot auth cache без TTL — stale tokens |
| 13 | MED | A05 | `config.py:17` | Debug mode по умолчанию включён |
| 14 | LOW | A05 | `Dockerfile.backend:12,22` | Dev dependencies + `--reload` в prod image |
| 15 | LOW | A06 | `docker-compose.yml:38,48` | Unpinned image tags (`:latest`) |
| 16 | LOW | A06 | `ci.yml` | Нет security scanning в CI |
| 17 | MED | A05 | `docker-compose.yml` | Source code volumes в production-like config |

---

## 5. АГЕНТ 3 — Frontend & Bot & Tests

### Frontend (8 проблем)

| # | Sev | Файл | Проблема |
|---|-----|------|----------|
| F-01 | MED | `api.ts:43-68` | API методы без generic type — возвращают `unknown` |
| F-02 | HIGH | `api.ts:7-25` | Нет refresh token, нет timeout, нет retry |
| F-03 | HIGH | `dashboard/page.tsx` | Статичные плейсхолдеры, нет auth guard |
| F-04 | MED | `dashboard/page.tsx:14-17` | `<a>` вместо `<Link>`, маршруты ведут в 404 |
| F-05 | MED | `page.tsx:20-24` | "API Docs" ведёт на frontend port (404) |
| F-06 | LOW | `package.json` | 4 зависимости объявлены, но не используются |
| F-07 | MED | `layout.tsx` | Нет error boundary, auth provider, Suspense |
| F-08 | MED | `next.config.ts` | Нет API proxy rewrites для production |

### Telegram Bot (21 проблема)

| # | Sev | Файл | Проблема |
|---|-----|------|----------|
| B-01 | CRIT | `middlewares/auth.py:22-23` | Auth cache без TTL — токены устаревают через 24ч |
| B-02 | HIGH | `middlewares/subscription.py:52-58` | Запрос подписки на каждое сообщение без кэша |
| B-03 | HIGH | `services/api_client.py:214,217` | Admin PATCH отправляет данные как query params |
| B-04 | HIGH | `services/api_client.py:17-21` | Race condition в singleton `get_client()` |
| B-05 | MED | `middlewares/rate_limit.py` | Документация говорит "Redis", реальность — in-memory dict |
| B-06 | MED | `middlewares/rate_limit.py:19-50` | Memory leak: dict растёт бесконечно |
| B-07 | MED | `main.py:35-41` | Rate limit не применяется к callback_query |
| B-08 | MED | `middlewares/auth.py:22` | Auth cache без лимита размера |
| B-09 | MED | `services/api_client.py:62-71` | Bracket access `data["access_token"]` без обработки |
| B-10 | MED | `services/api_client.py:219-226` | Хрупкая манипуляция URL через private attrs |
| B-11 | MED | `handlers/reports.py:157-163` | Не проверяется `api is None` перед вызовом |
| B-12 | MED | `handlers/content.py:42` | Поиск по UUID-префиксу — возможны коллизии |
| B-13 | MED | `handlers/admin.py:80+` | Raw exception messages отправляются пользователю |
| B-14 | MED | `main.py:32` | FSM хранится in-memory — теряется при рестарте |
| B-15 | LOW | `handlers/reports.py:457-459` | `_html_escape` не экранирует кавычки |
| B-16 | LOW | `handlers/competitors.py:51-52` | Нет валидации URL от пользователя |
| B-17 | LOW | `handlers/content.py:304` | Логика обрезки текста ошибочна для длины == 80 |
| B-18 | LOW | `middlewares/subscription.py:20-27` | Дублирование плановой логики backend ↔ bot |
| B-19 | LOW | `handlers/reports.py:462-479` | `_split_text` не режет параграфы > 4096 символов |
| B-20 | LOW | `handlers/common.py:113-118` | Кнопки просят набрать команду вместо прямого вызова |
| B-21 | LOW | `services/api_client.py:43-45` | Type annotations не соответствуют реальности |

### Tests & CI/CD (12 проблем)

| # | Sev | Файл | Проблема |
|---|-----|------|----------|
| T-01 | CRIT | `backend/tests/` | **Ноль тестов** бизнес-логики. Только инфраструктура |
| T-02 | HIGH | `bot/tests/` | Пустая директория — бот не тестируется вообще |
| T-03 | HIGH | `conftest.py:38-43` | `admin_headers` fixture не даёт admin-привилегий |
| T-04 | HIGH | `conftest.py:20-35` | Fixtures определены, но не используются ни одним тестом |
| T-05 | MED | `test_config.py:17` | Тесты зависят от dev defaults — хрупкие |
| T-06 | MED | `test_rate_limit.py:9-21` | Имя теста не соответствует содержанию |
| T-07 | MED | `Dockerfile.frontend:12` | `npm run dev` вместо `npm run build + start` |
| T-08 | MED | `Dockerfile.frontend:5` | `npm install` вместо `npm ci` |
| T-09 | MED | `docker-compose.yml:37-44` | Нет healthcheck для Qdrant и MinIO |
| T-10 | MED | `docker-compose.yml` | Hardcoded credentials в version control |
| T-11 | MED | `ci.yml:57-72` | Нет SECRET_KEY в CI, coverage пути не совпадают |
| T-12 | LOW | `ci.yml` | Нет кэширования зависимостей в CI pipeline |

---

## 6. АГЕНТ 4 — Architecture & Business Logic

**Найдено: 26 проблем (3 CRITICAL, 7 HIGH, 12 MEDIUM, 4 LOW)**

| # | Sev | Категория | Проблема |
|---|-----|-----------|----------|
| 1 | CRIT | Limit Enforcement | Месячный лимит задач считает all-time |
| 2 | CRIT | Limit Enforcement | Voice/video weekly лимиты не проверяются |
| 3 | CRIT | Billing | Webhook без идемпотентности — дубли подписок |
| 4 | HIGH | Scalability | Sync Stripe вызовы блокируют event loop |
| 5 | HIGH | Data Consistency | Publish endpoint ставит "published" даже при ошибке |
| 6 | HIGH | Business Logic | Данные собираются для expired подписок |
| 7 | HIGH | Scalability | Все конкуренты обрабатываются последовательно в одной задаче |
| 8 | HIGH | Scalability | In-memory rate limiter бесполезен с несколькими workers |
| 9 | HIGH | Data Consistency | Два разных способа поиска активной подписки |
| 10 | HIGH | Limit Enforcement | Celery-таски обходят все проверки лимитов/подписок |
| 11 | MED | Data Consistency | Удаление конкурента оставляет orphan-вектора в Qdrant |
| 12 | MED | Data Consistency | Нет distributed transaction Qdrant ↔ Postgres |
| 13 | MED | Scalability | N+1 запросы в deduplication pipeline |
| 14 | MED | Scalability | AI-генерация запускается синхронно в HTTP-handler |
| 15 | MED | Concurrency | Telethon session file конфликт при параллельном парсинге |
| 16 | MED | Coupling | Сервисы используют `os.getenv` вместо Settings |
| 17 | MED | Reliability | Celery `max_retries=3` объявлен, но `self.retry()` не вызывается |
| 18 | MED | Scalability | Нет task timeouts и queue routing в Celery |
| 19 | MED | Race Condition | Check-then-act при создании ресурсов с лимитами |
| 20 | MED | Infrastructure | Нет healthcheck для Qdrant и MinIO |
| 21 | MED | Security | Hardcoded default JWT secret |
| 22 | MED | Reliability | Нет circuit breakers для внешних API |
| 23 | LOW | Maintainability | Double commit pattern |
| 24 | LOW | Coupling | SalesAgent создаётся, но не используется в ReportGenerator |
| 25 | LOW | Coupling | VideoGenerator вызывает private метод VoiceGenerator |
| 26 | LOW | Scalability | N+1 запрос в admin user listing |

---

## 7. АГЕНТ 6 — Data Models & Schemas

**Найдено: 31 проблема (4 CRITICAL, 7 HIGH, 14 MEDIUM, 6 LOW)**

### CRITICAL

| # | Файл | Проблема |
|---|------|----------|
| C-01 | `alembic/versions/` | Нулевое количество миграций — невозможно развернуть БД |
| C-02 | `content_plan.py:54`, `content_task.py:38` | Конфликт ORM cascade vs FK `ondelete="SET NULL"` |
| C-03 | `competitor_post.py:71` | `backref` вместо explicit `back_populates` — stale ORM cache |
| C-04 | `database.py:27-28` | Автокоммит в `get_db()` конфликтует с явными commit в routes |

### HIGH

| # | Файл | Проблема |
|---|------|----------|
| H-01 | `schemas/user.py:18-24` | `UserUpdate` не содержит `brand_industry` |
| H-02 | `schemas/user.py:27-34` | `UserResponse` пропускает brand_description, tone_of_voice, timestamps |
| H-03 | `schemas/` | Нет Pydantic-схемы для `CompetitorPost` — данные недоступны через API |
| H-04 | `alembic/env.py:35` | Нет `compare_type=True` — autogenerate не видит изменения типов |
| H-05 | `content_task.py:43` | `platform` как `String(50)` вместо Enum |
| H-06 | `content.py:67` | `status="draft"` raw string вместо `PlanStatus.DRAFT` |
| H-07 | `schemas/content.py:44-49` | `ContentTaskUpdate` не содержит `content_type` и `metadata_json` |

### MEDIUM

| # | Проблема |
|---|----------|
| M-01 | Missing index на `content_tasks.status` |
| M-02 | Missing index на `reports.type` |
| M-03 | Missing composite index `(content_plan_id, status)` |
| M-04 | `engagement_rate` inferred Float → потеря precision |
| M-05 | `external_id` unique глобально — коллизии между platform-ами |
| M-06 | JSONB-колонки nullable, но имеют defaults — inconsistent |
| M-07 | Subscription model без `current_period_end` |
| M-08 | Нет валидации пароля в `UserCreate` |
| M-09 | `CompetitorCreate.platforms` не валидирует против Enum |
| M-10 | `GenerateResponse` имеет ненужный `from_attributes` |
| M-11 | Дублированный index на `competitor_posts.simhash` |
| M-12 | Дублированный index на `competitor_posts.competitor_id` |
| M-13 | `ContentTask.content_type` plain String без валидации |
| M-14 | `CompetitorResponse` пропускает `created_at`, `updated_at` |

---

## 8. ДЕДУПЛИЦИРОВАННЫЙ РЕЕСТР ВСЕХ ПРОБЛЕМ

Ниже — полный дедуплицированный список из 87 уникальных проблем, отсортированный по severity.

### CRITICAL (11)

| ID | Проблема | Файл(ы) |
|----|----------|---------|
| 001 | Telegram auth bypass — hash verification optional | `user_service.py:80` |
| 002 | Дефолтный JWT secret key в исходном коде | `config.py:18` |
| 003 | `scalar_first()` не существует — admin endpoint crashed | `admin.py:226` |
| 004 | Месячный лимит задач считает all-time | `content.py:162-165` |
| 005 | Celery tasks: string вместо UUID для user_id | `tasks.py:211` |
| 006 | Celery tasks: string literals вместо Enum values | `tasks.py:239,278,295` |
| 007 | Cascade conflict: ORM delete-orphan vs FK SET NULL | `content_plan.py:54`, `content_task.py:38` |
| 008 | Zero Alembic migrations — schema не развёртывается | `alembic/versions/` |
| 009 | Двойной commit + неясные transaction boundaries | `database.py:27-28`, `reports.py` |
| 010 | Stripe webhook без идемпотентности → дубликаты подписок | `billing_service.py:119-145` |
| 011 | Voice/video weekly лимиты никогда не проверяются | `reports.py:124-198` |

### HIGH (23)

| ID | Проблема | Файл(ы) |
|----|----------|---------|
| 012 | ValueError на невалидном UUID в JWT — 500 вместо 401 | `dependencies.py:32` |
| 013 | AVG query ignores LIMIT — averages all posts | `report_generator.py:289-296` |
| 014 | Sync Stripe API calls block async event loop | `billing_service.py:70,107,113,131` |
| 015 | Naive vs aware datetime → TypeError | `content.py:430` |
| 016 | `stripe.error` path invalid in stripe v6+ | `billing.py:65,84,100` |
| 017 | Publish endpoint marks "published" even on failure | `content.py:389-399` |
| 018 | Data collected for users with expired subscriptions | `tasks.py:54-93` |
| 019 | All competitors processed sequentially in one task | `tasks.py:38-93` |
| 020 | In-memory rate limiter useless with multiple workers | `rate_limit.py:32-42` |
| 021 | Two inconsistent subscription resolution strategies | `dependencies.py`, `billing_service.py` |
| 022 | Celery tasks bypass all limit/subscription checks | `tasks.py:199-254` |
| 023 | No password complexity enforcement | `auth.py:14` |
| 024 | X-Forwarded-For spoofing bypasses rate limit | `rate_limit.py:57-59` |
| 025 | 24h JWT, no refresh/revocation mechanism | `security.py:13` |
| 026 | All Docker containers run as root | `Dockerfile.*` |
| 027 | Missing .dockerignore — secrets in images | project root |
| 028 | Bot auth cache no TTL — permanent auth failure after 24h | `bot/middlewares/auth.py` |
| 029 | Bot admin PATCH sends data as query params | `bot/services/api_client.py:214` |
| 030 | Bot `get_client()` singleton race condition | `bot/services/api_client.py:17-21` |
| 031 | Zero business logic test coverage | `backend/tests/` |
| 032 | Zero bot test coverage | `bot/tests/` |
| 033 | UserResponse missing brand_description, tone_of_voice | `schemas/user.py:27-34` |
| 034 | No Pydantic schema for CompetitorPost — data inaccessible | `schemas/` |

### MEDIUM (38)

| ID | Категория | Проблема |
|----|-----------|----------|
| 035 | Backend | Double-commit pattern in report routes |
| 036 | Backend | Redis connection never closed on shutdown |
| 037 | Backend | String vs UUID mismatch in competitor ID filter |
| 038 | Backend | Raw strings for enum columns in ContentPlan |
| 039 | Backend | Health check creates unmanaged DB session |
| 040 | Architecture | Orphaned Qdrant vectors on competitor deletion |
| 041 | Architecture | No Qdrant/Postgres distributed transaction |
| 042 | Architecture | N+1 queries in deduplication pipeline |
| 043 | Architecture | AI generation runs synchronously in HTTP handlers |
| 044 | Architecture | Telethon session file conflict in concurrent parsing |
| 045 | Architecture | Services use os.getenv instead of centralized Settings |
| 046 | Architecture | Celery max_retries declared but retry() never called |
| 047 | Architecture | No task timeouts or queue routing in Celery |
| 048 | Architecture | Race condition on limit-checked resource creation |
| 049 | Architecture | No healthchecks on Qdrant and MinIO containers |
| 050 | Architecture | No circuit breakers on external API integrations |
| 051 | Security | Redis exposed without authentication |
| 052 | Security | Hardcoded DB credentials in docker-compose |
| 053 | Security | CORS not environment-aware |
| 054 | Security | Stripe subscription ID leaks to client |
| 055 | Security | Debug mode enabled by default |
| 056 | Security | Source code volumes in production-like config |
| 057 | Frontend | No token refresh, timeout, or retry in API client |
| 058 | Frontend | Dashboard static, no auth guard |
| 059 | Frontend | `<a>` instead of `<Link>`, routes 404 |
| 060 | Frontend | API Docs link points to wrong port |
| 061 | Frontend | No error boundary, auth provider, Suspense |
| 062 | Frontend | No API proxy rewrites for production |
| 063 | Bot | Subscription check on every message without caching |
| 064 | Bot | Rate limit docstring says Redis, reality is in-memory |
| 065 | Bot | Rate limit dict grows unboundedly (memory leak) |
| 066 | Bot | Rate limit not applied to callback queries |
| 067 | Bot | FSM stored in-memory, lost on restart |
| 068 | Data | Missing indexes: content_tasks.status, reports.type |
| 069 | Data | external_id unique globally — cross-platform collisions |
| 070 | Data | Subscription model missing current_period_end |
| 071 | Data | ContentTask.platform is String instead of Enum |
| 072 | Data | ContentTaskUpdate missing content_type, metadata_json |

### LOW (15)

| ID | Проблема |
|----|----------|
| 073 | Services bypass centralized Settings via os.getenv |
| 074 | CORS hardcoded to localhost:3000 |
| 075 | Dev dependencies + --reload in production Dockerfile |
| 076 | Unpinned Docker image tags (:latest) |
| 077 | No security scanning in CI pipeline |
| 078 | Unused SalesAgent in ReportGenerator |
| 079 | VideoGenerator calls private VoiceGenerator method |
| 080 | N+1 query in admin user listing |
| 081 | Frontend: 4 unused npm dependencies |
| 082 | Bot: _html_escape doesn't escape quotes |
| 083 | Bot: No URL validation from user input |
| 084 | Bot: _split_text can exceed 4096 Telegram limit |
| 085 | Bot: Buttons ask to type command instead of direct action |
| 086 | Data: Redundant indexes on competitor_posts |
| 087 | Data: alembic.ini hardcodes database URL with credentials |

---

## 9. ПЛАН ИЗМЕНЕНИЙ

### ФАЗА 0 — Немедленные исправления (блокеры деплоя)

> **Приоритет: МАКСИМАЛЬНЫЙ. Без этих изменений продукт нельзя запускать.**

| # | Действие | Файл(ы) | Оценка |
|---|----------|---------|--------|
| 1 | **Сделать Telegram hash verification обязательной** — убрать условный `if`, отклонять запросы без `hash`/`auth_date`, добавить проверку staleness (5 мин) | `user_service.py`, `auth.py` | 2ч |
| 2 | **Убрать дефолтный secret_key** — `secret_key: str` без default, добавить startup validator | `config.py`, `main.py` | 1ч |
| 3 | **Исправить `scalar_first()` → `.scalars().first()`** | `admin.py:226` | 5мин |
| 4 | **Добавить фильтр `created_at >= month_start`** в подсчёт задач | `content.py:162-165` | 30мин |
| 5 | **Конвертировать `user_id` в UUID** в Celery-тасках | `tasks.py` | 30мин |
| 6 | **Заменить string literals на Enum values** в Celery-тасках | `tasks.py` | 1ч |
| 7 | **Создать initial Alembic migration** `alembic revision --autogenerate` | `alembic/` | 1ч |
| 8 | **Добавить idempotency check** в Stripe webhook handler | `billing_service.py` | 2ч |
| 9 | **Добавить вызов `check_voice_limit`/`check_video_limit`** | `reports.py` | 1ч |

**Итого Фаза 0: ~9 часов**

---

### ФАЗА 1 — Критические исправления (1-й спринт)

> **Приоритет: ВЫСОКИЙ. Исправления для стабильности и безопасности.**

| # | Действие | Файл(ы) |
|---|----------|---------|
| 10 | Выбрать единую стратегию транзакций (убрать auto-commit или убрать явные commit) | `database.py`, все routers |
| 11 | Разрешить cascade conflict: CASCADE vs SET NULL — выбрать одно | `content_plan.py`, `content_task.py` |
| 12 | Заменить `backref` на explicit `back_populates` в CompetitorPost | `competitor_post.py`, `competitor.py` |
| 13 | Обернуть Stripe вызовы в `asyncio.to_thread()` | `billing_service.py` |
| 14 | Обработать ValueError в JWT UUID parsing | `dependencies.py` |
| 15 | Исправить AVG query — subquery для last 30 posts | `report_generator.py` |
| 16 | Добавить timezone validation для `scheduled_at` | `content.py`, `schemas/content.py` |
| 17 | Обновить `stripe.error` → `stripe.StripeError` | `billing.py` |
| 18 | Проверить `pub_result["status"]` перед установкой published | `content.py:389-399` |
| 19 | Добавить password complexity validation (`min_length=8`) | `schemas/user.py`, `auth.py` |
| 20 | Исправить X-Forwarded-For — trusted proxy list | `rate_limit.py` |
| 21 | Добавить `.dockerignore` (`.env`, `.git`, `node_modules`, `__pycache__`) | project root |
| 22 | Добавить non-root USER в Dockerfiles | `Dockerfile.backend`, `Dockerfile.bot`, `Dockerfile.frontend` |
| 23 | Установить `debug: bool = False` по умолчанию | `config.py` |
| 24 | Добавить TTL в bot auth cache (`cachetools.TTLCache`) | `bot/middlewares/auth.py` |
| 25 | Исправить admin API client: `json=body` вместо `params=body` | `bot/services/api_client.py` |

**Итого Фаза 1: ~20 часов (1 спринт)**

---

### ФАЗА 2 — Архитектурные улучшения (2-3 спринт)

> **Приоритет: СРЕДНИЙ. Масштабируемость и надёжность.**

| # | Действие |
|---|----------|
| 26 | Перевести rate limiter на Redis-backed implementation |
| 27 | Вынести AI-генерацию в Celery background tasks (вместо HTTP handler) |
| 28 | Разделить Celery на очереди: `default`, `media`, `collection` |
| 29 | Добавить `soft_time_limit` / `time_limit` на все Celery tasks |
| 30 | Реализовать `self.retry()` с exponential backoff в Celery tasks |
| 31 | Fan-out data collection: одна sub-task на конкурента |
| 32 | Фильтровать конкурентов по активной подписке при сборе данных |
| 33 | Батчить external_id проверки при deduplication (eliminate N+1) |
| 34 | Добавить circuit breakers для внешних API (Anthropic, ElevenLabs, HeyGen, YouTube) |
| 35 | Перенести все `os.getenv()` вызовы на централизованный `Settings` |
| 36 | Добавить очистку Qdrant vectors при удалении конкурента |
| 37 | Добавить reconciliation job: Qdrant ↔ Postgres |
| 38 | Перевести CORS origins на environment variable |
| 39 | Добавить healthcheck для Qdrant и MinIO в docker-compose |
| 40 | Создать `docker-compose.prod.yml` без volumes и `--reload` |

**Итого Фаза 2: ~40 часов (2 спринта)**

---

### ФАЗА 3 — Data Model & Schema (3-4 спринт)

| # | Действие |
|---|----------|
| 41 | Добавить missing поля в `UserUpdate` и `UserResponse` |
| 42 | Создать `CompetitorPostResponse` schema + API endpoints |
| 43 | Включить `compare_type=True` в Alembic env.py |
| 44 | Заменить `ContentTask.platform` String → Enum |
| 45 | Добавить `ContentTaskUpdate.content_type`, `metadata_json` |
| 46 | Добавить missing indexes: `content_tasks.status`, `reports.type` |
| 47 | Изменить `external_id` unique → composite unique `(external_id, platform)` |
| 48 | Добавить `nullable=False` на JSONB columns с defaults |
| 49 | Добавить `current_period_end` в Subscription model |
| 50 | Убрать redundant indexes на `competitor_posts` |
| 51 | Добавить валидацию `platforms` против Enum в `CompetitorCreate` |
| 52 | Добавить unique partial index на `subscriptions(user_id) WHERE status IN ('active', 'trialing')` |

**Итого Фаза 3: ~24 часа (1-2 спринта)**

---

### ФАЗА 4 — Frontend, Bot, Tests (4-5 спринт)

| # | Действие |
|---|----------|
| 53 | Добавить JWT refresh flow в frontend API client |
| 54 | Реализовать auth guard на dashboard pages |
| 55 | Заменить `<a>` на `<Link>`, создать недостающие route pages |
| 56 | Добавить error boundaries и Suspense в layout |
| 57 | Настроить API proxy в next.config.ts |
| 58 | Кэшировать subscription check в bot middleware |
| 59 | Перевести bot FSM storage на Redis |
| 60 | Добавить rate limiting на callback_query |
| 61 | Исправить bot `get_client()` race condition с asyncio.Lock |
| 62 | Добавить security scanning в CI (pip-audit, npm audit, trivy) |
| 63 | Написать тесты бизнес-логики: auth flow, billing, content pipeline |
| 64 | Написать тесты для bot handlers |
| 65 | Добавить dependency caching в CI pipeline |

**Итого Фаза 4: ~60 часов (2-3 спринта)**

---

### ДОРОЖНАЯ КАРТА

```
Неделя 1-2:   ФАЗА 0 (блокеры) + ФАЗА 1 (критические)
Неделя 3-4:   ФАЗА 2 (архитектура)
Неделя 5-6:   ФАЗА 3 (data models)
Неделя 7-10:  ФАЗА 4 (frontend, bot, tests)
```

**Общий объём: ~153 часа разработки (~4-5 разработчиков × 2 недели или 1-2 разработчика × 6-8 недель)**

---

## ЗАКЛЮЧЕНИЕ

Проект имеет солидную архитектуру и амбициозный функционал, но содержит **11 критических точек слома**, которые делают его непригодным для production-деплоя в текущем состоянии. Наиболее опасные:

1. **Authentication bypass** через Telegram (BREAK-01) — позволяет доступ к любому аккаунту
2. **Предсказуемый JWT secret** (BREAK-02) — позволяет подделку токенов
3. **Сломанные Celery-таски** (BREAK-05, BREAK-06) — background processing не работает
4. **Нулевые миграции** (BREAK-08) — невозможно развернуть БД
5. **Обход billing лимитов** (BREAK-04, BREAK-11) — пользователи могут не платить за ресурсы

Рекомендуется немедленно начать с Фазы 0, затем последовательно двигаться по плану.

---

*Отчёт сгенерирован автоматически командой из 6 AI-агентов аудита. Дата: 2026-02-06.*
