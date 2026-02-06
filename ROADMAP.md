# ROADMAP: AI Marketing Intelligence Platform

## Текущее состояние проекта (As-Is)

### Реализовано (Phases 0-5)

| Модуль | Статус | Описание |
|--------|--------|----------|
| Auth (email + Telegram) | Done | JWT, регистрация, Telegram Web App |
| Billing (Stripe) | Done | 4 тарифа, checkout, webhook, portal |
| Competitor Tracking | Done | CRUD, мультиплатформенность |
| Parsers (4 из 5) | Done | Telegram, YouTube, VK, Website |
| Vector DB (Qdrant) | Done | Embeddings, семантический поиск, RAG |
| AI Agents (3 типа) | Partial | Analyst + Marketer используются, **Sales НЕ интегрирован** |
| Content Generation | Done | AI-генерация, воркфлоу approve/reject |
| Content Publishing | Partial | Telegram + VK. **YouTube/Instagram/Website не поддержаны** |
| Reports (Digest/Alert) | Done | Еженедельные дайджесты, алерты |
| Media (PDF/Voice/Video) | Done | ElevenLabs, HeyGen, charts |
| Telegram Bot | Done | Onboarding, команды, FSM, middleware |
| Admin Panel | Done | API + бот-команды |
| Frontend Dashboard | **Scaffold** | Только заглушки, нет реальных страниц |
| Tests | Basic | 6 файлов, базовое покрытие |
| CI/CD | Done | GitHub Actions: lint, test, build |

---

## Выявленные пробелы и незавершённые модули

### 1. Instagram Parser (отсутствует)
- **Проблема:** Платформа `instagram` есть в enum `Platform`, в `PLATFORM_LIMITS`, но парсер не написан
- **Файл:** `backend/app/services/parsers/__init__.py` — Instagram отсутствует в `PARSER_MAP`
- **Влияние:** Пользователи могут добавить Instagram-конкурента, но данные собираться не будут

### 2. SalesAgent не интегрирован
- **Проблема:** `SalesAgent` создан в `report_generator.py:35` (`self.sales = SalesAgent()`), но **нигде не вызывается**
- **Влияние:** Функциональность sales-анализа (воронки, CTA, промо-паттерны) недоступна

### 3. Публикация на 3 из 5 платформ не работает
- **Проблема:** `publisher.py:45-50` — YouTube, Instagram, Website возвращают `"unsupported"`
- **Влияние:** Autopilot неполноценен для этих платформ

### 4. Frontend — только заглушки
- **Проблема:** Dashboard показывает "—" в карточках, страницы competitors/content/reports не существуют
- **Влияние:** Веб-интерфейс неработоспособен, только бот функционирует

### 5. Тесты — минимальное покрытие
- **Проблема:** Нет тестов для ключевой бизнес-логики (agents, parsers, publisher, content generator)
- **Влияние:** Риск регрессий при добавлении новых фич

---

## Новые функции (To-Be)

### Phase 6: Достройка пробелов + Аналитический дашборд

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 6.1 | **Instagram Parser** | HIGH | Нет конфликтов. Нужно добавить в `PARSER_MAP`, написать парсер по образцу `vk_parser.py`. Instagram API ограничен — потребуется web-scraping fallback |
| 6.2 | **SalesAgent интеграция** | HIGH | Потенциальный конфликт с `report_generator.py` — нужно добавить вызов `self.sales.run()` в `generate_digest()` без нарушения текущего формата отчётов. Нужен новый ReportType `SALES` или расширение DIGEST |
| 6.3 | **Dashboard: Overview с реальными данными** | HIGH | Конфликт с текущим `page.tsx` — полная переписка. Нужен API-клиент для авторизации (NextAuth integration). Зависимость от `/api/v1/competitors/usage/summary` и новых эндпоинтов статистики |
| 6.4 | **Dashboard: Competitors page** | HIGH | Нет конфликтов. Создание новой страницы. Зависит от API `/api/v1/competitors` |
| 6.5 | **Dashboard: Content page** | HIGH | Нет конфликтов. Зависит от API `/api/v1/content` |
| 6.6 | **Dashboard: Reports page** | HIGH | Нет конфликтов. Зависит от API `/api/v1/reports` |

### Phase 7: Расширенная аналитика и Smart-функции

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 7.1 | **Trend Detection (тренды)** | HIGH | Нужна новая таблица `trends` в БД. Конфликт: расширение `CompetitorPost` — добавление поля `topic_tags` (JSONB). Зависит от Qdrant кластеризации. Нужна Celery-задача для периодического анализа |
| 7.2 | **Sentiment Analysis** | MEDIUM | Потенциальный конфликт с `CompetitorPost` — добавление поля `sentiment_score`. Влияет на `pipeline.py` — нужно добавить этап sentiment в обработку. Зависит от AI-модели (Claude или отдельная модель) |
| 7.3 | **Competitor Comparison Dashboard** | MEDIUM | Нет конфликтов с бэкендом. Нужен новый API endpoint `/api/v1/analytics/compare`. Frontend: новая страница |
| 7.4 | **Content Performance Tracking** | MEDIUM | Конфликт: нужно расширение `ContentTask` — добавление полей метрик (views, likes post-publication). Нужна Celery-задача для обратного сбора метрик опубликованного контента |
| 7.5 | **Smart Scheduling (лучшее время постинга)** | MEDIUM | Зависит от 7.4 (нужны метрики по часам/дням). Конфликт с `publisher.py` — нужно расширить логику auto-schedule |

### Phase 8: Мультиканальность и интеграции

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 8.1 | **YouTube auto-publish** | MEDIUM | Конфликт с `publisher.py` — добавление `_publish_youtube()`. Нужен OAuth2 flow для YouTube Data API. Требует расширения `.env` |
| 8.2 | **Notification System (email + in-app)** | HIGH | Нет прямых конфликтов. Нужна новая модель `Notification` в БД. Требует email-сервис (SendGrid/SES). Интеграция с `check_alerts()` — вместо просто создания Report, отправлять уведомления |
| 8.3 | **Webhook API (outgoing)** | MEDIUM | Нет конфликтов. Новая модель `WebhookEndpoint`. Новый роутер `/api/v1/webhooks`. Триггер при создании Report/Alert |
| 8.4 | **Multi-language support (i18n)** | LOW | Серьёзный конфликт: все AI-промпты на русском (`agents/*.py`). Нужна система шаблонов промптов с переключением языка. Бот-хендлеры тоже на русском. Потенциально ломает все строковые output'ы |

### Phase 9: Командная работа и масштабирование

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 9.1 | **Team/Organization accounts** | HIGH | Серьёзный конфликт: текущая модель `User` — один пользователь = один аккаунт. Нужна новая модель `Organization` + `TeamMember` + роли (owner/editor/viewer). Влияет на ВСЕ запросы с `user_id` — нужно переделывать на `organization_id`. Ломает `limits_service.py`, `billing_service.py` |
| 9.2 | **Audit Log** | MEDIUM | Нет конфликтов. Новая модель `AuditEvent`. Middleware для автоматической записи действий |
| 9.3 | **API Rate Limiting per-plan** | LOW | Частично реализован в `rate_limit.py`. Нужна интеграция с Subscription model для per-plan лимитов |
| 9.4 | **Data Export (CSV/Excel)** | MEDIUM | Нет конфликтов. Новые эндпоинты для экспорта competitors, reports, content |

### Phase 10: Кибер SEO&GEO — Фундамент

> **Подробности:** см. [CYBER_SEO_GEO_INTEGRATION.md](./CYBER_SEO_GEO_INTEGRATION.md)

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 10.1 | **Модели данных (BlogPost, BlogCategory)** | HIGH | Новые таблицы, не конфликтует с `content_tasks`. Alembic миграция, расширение User (author_bio, author_photo_url — nullable) |
| 10.2 | **Агентная инфраструктура** | HIGH | AgentConfig + AgentOrchestrator (WorkflowDAG). Обратно-совместимое расширение BaseAgent. 9 новых агентов: Investigator, Architect, ResearchManager, Journalist, Writer, Editor, Structurer, ArtDirector, SEOSpec |
| 10.3 | **WordPress Publisher** | HIGH | Конфликт с `publisher.py` — добавление `_publish_wordpress()`. Нужен WP REST API клиент. Расширение `.env` (WP_API_URL, WP_USERNAME, WP_APP_PASSWORD) |
| 10.4 | **Perplexity Research Tool** | MEDIUM | Новый сервис `perplexity_client.py`, интеграция как tool для InvestigatorAgent и ResearchManagerAgent |
| 10.5 | **Image Generator Service** | MEDIUM | Новый сервис `image_generator.py`, Replicate/Kie.ai API, S3 upload через MinIO (готова инфраструктура) |

### Phase 11: SEO Content Pipeline

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 11.1 | **SEO Pipeline Orchestrator** | HIGH | `seo_pipeline.py` — мастер-оркестратор. WF1 Brain (Investigator→Architect→Validator), WF2 Hook (Journalist→ArtDirector), WF3 Body Loop (Writer→Editor→Structurer), WF4 Assembly (Conclusion+FAQ+Author), WF5 Publisher (WordPress + revalidation). Зависит от 10.2 AgentOrchestrator |
| 11.2 | **Blog API Router** | HIGH | Новый роутер `/api/v1/blog/`. CRUD для BlogPost, категории, теги, fulltext + Qdrant семантический поиск. Зависит от 10.1 моделей |
| 11.3 | **SEO Pipeline Celery Tasks** | HIGH | Celery chain/chord/group: brain→hook→body→assembly→publish→index. WorkflowEngine для управления пайплайнами, WorkflowRun/WorkflowStepLog модели для трекинга, SSE для real-time статуса |

### Phase 12: SEO Frontend (Next.js Blog)

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 12.1 | **Blog Pages** | HIGH | `/blog` (ISR 3600s), `/blog/[slug]` (ISR 60s), `/blog/category/[slug]`. Конфликт с Phase 6.3-6.6 Dashboard — использовать общие UI компоненты. Раздельные пути: `/dashboard/*` vs `/blog/*` |
| 12.2 | **SEO Components** | HIGH | Schema.org (Article, FAQ, Breadcrumb), dynamic meta tags, sitemap.xml, robots.txt, Table of Contents, Breadcrumbs |
| 12.3 | **UX Blog Components** | MEDIUM | AuthorBox, RelatedPosts (Qdrant similarity), FAQBlock с аккордеоном, ShareButtons, ReadingProgress bar |

### Phase 13: Google Sheets + Workflow автоматизация

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 13.1 | **WorkflowEngine + модели трекинга** | HIGH | `workflow_engine.py` — управление пайплайнами. Модели `WorkflowRun` + `WorkflowStepLog` (Alembic миграция). Redis pub/sub для real-time статусов. SSE endpoint `/api/v1/workflows/{id}/stream` |
| 13.2 | **Google Sheets интеграция** | MEDIUM | `google_sheets_sync.py` (gspread), CONVEYOR/PUBLISHED/SETTINGS листы. Celery Beat polling каждые 5 мин. Redis distributed lock для дедупликации. Нужен `GOOGLE_SHEETS_CREDENTIALS_JSON` |
| 13.3 | **Workflow API Router** | MEDIUM | `/api/v1/workflows/` — start, status, stream (SSE), cancel, retry, logs. Зависит от 13.1 WorkflowEngine |
| 13.4 | **Celery SEO Worker** | MEDIUM | Отдельный Celery worker на очередях `seo` + `sheets` (тот же Docker image, другая команда). Не блокирует основной worker парсинга/дайджестов |

### Phase 14: Качество и мониторинг SEO

| # | Фича | Приоритет | Конфликты / Зависимости |
|---|-------|-----------|------------------------|
| 14.1 | **Content Quality Checks** | HIGH | AI Detection score (EditorAgent), SEO Checklist автоматический, Schema.org валидация, Yoast-like scoring в pipeline |
| 14.2 | **Индексация** | MEDIUM | Google IndexNow API, Yandex Webmaster API, Search Console интеграция, мониторинг позиций (опционально, SEMRUSH/DataForSEO) |

---

## Анализ конфликтов (подробный)

### Критические конфликты (требуют осторожной реализации)

#### 1. Team Accounts vs User Model
- **Файлы затронуты:** `user.py`, `subscription.py`, `limits_service.py`, `billing_service.py`, все роутеры с `current_user`, бот-хендлеры
- **Суть:** Вся система построена на `user_id` как владельце данных. Переход на `organization_id` затрагивает ~30 файлов
- **Рекомендация:** Реализовывать в последнюю очередь (Phase 9). Использовать паттерн "User belongs to Organization" с обратной совместимостью — каждый User автоматически создаёт Organization при миграции

#### 2. i18n vs Russian-only prompts
- **Файлы затронуты:** `analyst.py`, `marketer.py`, `sales.py`, все bot handlers, `report_generator.py`
- **Суть:** Все system prompts, bot messages, report templates жёстко на русском
- **Рекомендация:** Низкий приоритет. Если реализовывать — через Jinja2 templates с locale-файлами

#### 3. Trend Detection vs CompetitorPost model
- **Файлы затронуты:** `competitor_post.py`, `pipeline.py`, Alembic migration
- **Суть:** Добавление `topic_tags` и `sentiment_score` требует миграции БД и обновления pipeline
- **Рекомендация:** Добавлять поля как nullable, обновлять pipeline с backward-compatible fallback

### Средние конфликты

#### 4. Content Performance vs ContentTask model
- **Файлы:** `content_task.py`, `publisher.py`, новая Celery-задача
- **Суть:** После публикации нужно собирать метрики. Требует новых полей в ContentTask или отдельной таблицы
- **Рекомендация:** Отдельная таблица `ContentMetrics` с FK на `ContentTask`

#### 5. SalesAgent vs Report flow
- **Файлы:** `report_generator.py`, `reports.py` (router), `report.py` (model)
- **Суть:** Нужно решить — отдельный тип отчёта `SALES` или секция в DIGEST
- **Рекомендация:** Новый тип `ReportType.SALES` + отдельный endpoint `POST /reports/sales`

#### 6. Notification System vs Alert flow
- **Файлы:** `report_generator.py:check_alerts()`, новый notification service
- **Суть:** Текущие алерты только создают Report. Нужно добавить отправку уведомлений
- **Рекомендация:** Event-driven подход — после создания Alert, emit событие, notification service подписан

### Минимальные конфликты (безопасно добавлять)

- Instagram Parser — изолированный модуль, только добавление в `PARSER_MAP`
- Dashboard pages — фронтенд, не затрагивает бэкенд
- Webhook API — новый роутер, изолирован
- Data Export — новые эндпоинты, изолированы
- Audit Log — middleware, не ломает существующую логику

### Конфликты Кибер SEO&GEO (Phases 10-14)

#### 7. BaseAgent расширение для 12 агентов
- **Файлы:** `base.py`, новые `agents/seo/*.py`
- **Суть:** Нужен `AgentConfig` (per-agent model/temperature/rag_limit) и `AgentOrchestrator` (WorkflowDAG)
- **Рекомендация:** Обратно-совместимое расширение — AgentConfig с дефолтами, AgentOrchestrator как отдельный класс

#### 8. PublisherService расширение (WordPress)
- **Файлы:** `publisher.py`
- **Суть:** Добавление `_publish_wordpress()`, WP REST API клиент
- **Рекомендация:** Аналогично `_publish_telegram()` — новый elif branch, изолирован

#### 9. ContentTask vs BlogPost
- **Файлы:** `content_task.py` (существующий), `blog_post.py` (новый)
- **Суть:** BlogPost — отдельная таблица с SEO-полями (slug, meta, schema.org). НЕ расширение ContentTask
- **Рекомендация:** Полная изоляция — разные модели, разные роутеры, разные пайплайны

#### 10. Next.js Dashboard vs Blog
- **Файлы:** `frontend/src/app/dashboard/*` vs `frontend/src/app/blog/*`
- **Суть:** Оба используют Next.js 15, но Blog требует ISR, SEO meta, sitemap
- **Рекомендация:** Общие UI-компоненты, раздельные layouts. Blog = public, Dashboard = auth-protected

---

## Рекомендуемый порядок реализации

```
Phase 6 (Достройка пробелов)           ← НАЧАТЬ ЗДЕСЬ
├── 6.1 Instagram Parser
├── 6.2 SalesAgent Integration
├── 6.3 Dashboard: Overview (real data)
├── 6.4 Dashboard: Competitors page
├── 6.5 Dashboard: Content page
└── 6.6 Dashboard: Reports page

Phase 10 (Фундамент SEO&GEO)           ← ПАРАЛЛЕЛЬНО С 6.3-6.6
├── 10.1 BlogPost + BlogCategory models
├── 10.2 AgentOrchestrator + 9 агентов
├── 10.3 WordPress Publisher
├── 10.4 Perplexity Tool
└── 10.5 Image Generator

Phase 11 (SEO Pipeline)
├── 11.1 SEO Pipeline Orchestrator
├── 11.2 Blog API Router
└── 11.3 Celery Tasks для pipeline

Phase 12 (SEO Frontend) + Phase 6.3-6.6 (Dashboard)
├── 12.1 Blog Pages (ISR)
├── 12.2 SEO Components
├── 12.3 UX Blog Components
└── Dashboard pages (общие UI-компоненты)

Phase 7 (Smart-аналитика)
├── 7.1 Trend Detection
├── 7.2 Sentiment Analysis
├── 7.3 Competitor Comparison
├── 7.4 Content Performance Tracking
└── 7.5 Smart Scheduling

Phase 13 (Google Sheets + Workflow автоматизация)
├── 13.1 WorkflowEngine + модели трекинга
├── 13.2 Google Sheets интеграция (Celery Beat polling)
├── 13.3 Workflow API Router + SSE
└── 13.4 Celery SEO Worker (выделенная очередь)

Phase 8 (Интеграции)
├── 8.1 YouTube auto-publish
├── 8.2 Notification System
├── 8.3 Webhook API
└── 8.4 i18n (optional)

Phase 14 (Качество SEO)
├── 14.1 Content Quality Checks
└── 14.2 Индексация

Phase 9 (Масштабирование)               ← ПОСЛЕДНЯЯ (ломающее изменение)
├── 9.1 Team/Organization accounts
├── 9.2 Audit Log
├── 9.3 Per-plan rate limiting
└── 9.4 Data Export
```

---

## Зависимости между фичами

```
ОРИГИНАЛЬНЫЕ ФИЧИ:
6.1 Instagram Parser ──────────────────────── (независим)
6.2 SalesAgent ────────────────────────────── (независим)
6.3-6.6 Dashboard ─────────────────────────── (независимы от бэкенда)
7.1 Trends ──── зависит от ── 6.1 (больше данных = лучше тренды)
7.2 Sentiment ── зависит от ── pipeline.py (расширение)
7.4 Performance ─ зависит от ── publisher.py (обратный сбор)
7.5 Scheduling ── зависит от ── 7.4 (нужны метрики по времени)
8.1 YT Publish ── зависит от ── OAuth2 setup
8.2 Notifications ─ зависит от ── email service setup
9.1 Teams ──── зависит от ── ВСЕ предыдущие фазы (ломающее изменение)

КИБЕР SEO&GEO:
10.1 BlogPost models ──────────────────────── (независим, новые таблицы)
10.2 AgentOrchestrator ── зависит от ── BaseAgent (расширение)
10.3 WordPress Publisher ── зависит от ── publisher.py (расширение)
10.4 Perplexity Tool ─────────────────────── (независим)
10.5 Image Generator ─────────────────────── (независим, MinIO готов)
11.1 SEO Pipeline ──── зависит от ── 10.2 + 10.4 + 10.5
11.2 Blog API ──── зависит от ── 10.1
11.3 Celery Tasks ── зависит от ── 11.1
12.1 Blog Pages ──── зависит от ── 11.2 (API)
12.2 SEO Components ── зависит от ── 12.1
12.3 UX Components ── зависит от ── 12.1
13.1 WorkflowEngine ── зависит от ── Redis (есть) + PostgreSQL (новые модели)
13.2 Google Sheets ── зависит от ── Celery Beat (есть) + gspread
13.3 Workflow API ──── зависит от ── 13.1 + FastAPI (есть)
13.4 Celery SEO Worker ── зависит от ── celery_app.py (расширение очередей)
14.1 Quality Checks ── зависит от ── 11.1 (pipeline)
14.2 Индексация ──── зависит от ── 12.1 (blog должен быть live)

ПЕРЕКРЁСТНЫЕ ЗАВИСИМОСТИ:
Phase 6.3-6.6 Dashboard ←→ Phase 12 Blog (общие UI компоненты)
Phase 7.1 Trends ──────────→ Phase 11 (тренды для тем статей)
Phase 7.2 Sentiment ───────→ Phase 11 EditorAgent (тональность)
Phase 8.2 Notifications ───→ Phase 13 WorkflowEngine (уведомления о статьях)
Phase 9.1 Teams ───────────→ BlogPost.user_id → organization_id
```
