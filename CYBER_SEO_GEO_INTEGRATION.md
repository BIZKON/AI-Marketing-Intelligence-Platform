# Кибер SEO&GEO — План интеграции в AI Marketing Intelligence Platform

## 1. Резюме анализа

### Что такое Кибер SEO&GEO
Автоматизированная система создания SEO/GEO-оптимизированных статей с конвейерным
производством контента. Включает:
- **12 AI-агентов** с мультиагентной оркестрацией
- **7+1 Celery Workflow** для управления конвейером (chain/chord/group)
- **WordPress Headless CMS** как бэкенд для контента
- **Next.js SEO-фронтенд** для блога
- **Google Sheets** как очередь задач и трекер
- **Perplexity API** для исследований/фактчекинга
- **Kie.ai (Flux/Midjourney)** для генерации изображений

### Что уже есть в платформе (совпадения)

| Компонент ТЗ | Аналог в платформе | Переиспользуемость |
|---------------|-------------------|-------------------|
| Claude AI агенты | `BaseAgent` + 3 агента (Analyst, Marketer, Sales) | **90%** — нужно только наследование |
| Генерация контента | `ContentGenerator` + `MarketerAgent` | **70%** — нужны SEO-промпты |
| Публикация | `PublisherService` (Telegram/VK) | **30%** — нужен WordPress publisher |
| Next.js фронтенд | Scaffold dashboard (Next.js 15) | **50%** — нужны SEO-страницы блога |
| Фоновые задачи | Celery + Redis + Beat | **90%** — расширить chains/chords для SEO pipeline |
| Хранение файлов | MinIO (S3) | **95%** — готово для изображений |
| Embeddings/RAG | Qdrant + OpenAI embeddings | **85%** — можно для перелинковки |
| PostgreSQL | Async SQLAlchemy + JSONB | **95%** — нужны новые модели |
| Docker инфраструктура | docker-compose с 9 сервисами | **95%** — добавить Celery SEO Worker (тот же image) |

---

## 2. Архитектурное решение: Единый Celery-native подход

```
┌──────────────────────────────────────────────────────────────────┐
│                AI Marketing Intelligence Platform                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌──────────────────────┐    ┌────────────────────────────────┐ │
│   │  Celery Worker        │    │  Celery Worker SEO             │ │
│   │  (default queue)      │    │  (seo + sheets queues)         │ │
│   │  ──────────────────  │    │  ────────────────────────────  │ │
│   │  • Data parsing       │    │  • SEO Pipeline chains/chords  │ │
│   │  • Weekly digests     │    │  • Google Sheets polling (Beat)│ │
│   │  • Auto-publish       │    │  • Multi-agent orchestration   │ │
│   │  • Voice/Video        │    │  • Image generation            │ │
│   │  • Alerts             │    │  • WordPress publishing        │ │
│   └───────┬──────────────┘    └──────────┬─────────────────────┘ │
│           │    Celery Beat (расписание)   │                       │
│           │    ─────────────────────────  │                       │
│           │    • poll_google_sheets (5m)  │                       │
│           │    • retry_stale_workflows    │                       │
│           │    • existing schedules       │                       │
│   ┌───────┴──────────────────────────────┴─────────────────────┐ │
│   │              FastAPI Backend (Unified)                       │ │
│   │  • Workflow Router (/api/v1/workflows/) + SSE stream        │ │
│   │  • Blog Router (/api/v1/blog/)                              │ │
│   │  • Existing routers (auth, billing, content...)             │ │
│   │  • 12+ AI Agents (BaseAgent + AgentOrchestrator)            │ │
│   │  • WorkflowEngine (start/status/cancel/retry)               │ │
│   └───────┬───────────────────────────────┬────────────────────┘ │
│           │                               │                      │
│   ┌───────┴──────────┐    ┌──────────────┴─────────────────────┐ │
│   │ PostgreSQL + Redis│    │ WordPress Headless CMS             │ │
│   │ Qdrant + MinIO   │    │ (External)                         │ │
│   │                  │    │                                     │ │
│   │ WorkflowRun      │    │ REST API + Application Passwords   │ │
│   │ WorkflowStepLog  │    └─────────────────────────────────────┘ │
│   │ BlogPost         │                                            │
│   │ BlogCategory     │                                            │
│   └──────────────────┘                                            │
│                                                                   │
│   ┌─────────────────────────────────────────────────────────────┐ │
│   │           Next.js 15 Frontend                                │ │
│   │  • /dashboard/* (существующий, auth-protected)               │ │
│   │  • /blog/* (NEW: SEO-оптимизированный блог, public)          │ │
│   │  • Sitemap, robots.txt, Schema.org                           │ │
│   └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Почему единый Celery-подход (вместо N8N):
1. **Celery** расширяется для SEO/GEO через chain/chord/group — DAG-подобные пайплайны
2. **Нет новых внешних зависимостей** — используем существующие Redis, Celery, PostgreSQL
3. **Google Sheets polling** через Celery Beat (каждые 5 мин) заменяет N8N trigger
4. **WorkflowEngine + Redis pub/sub + SSE** заменяет N8N UI для real-time трекинга
5. **Выделенный Celery SEO Worker** (тот же Docker image) изолирует нагрузку от основного worker
6. **Единый FastAPI** роутит запросы, предоставляет `/api/v1/workflows/` API
7. **Нулевой риск** для существующей функциональности

---

## 3. Карта конфликтов и решений

### Критические конфликты

| # | Конфликт | Детали | Решение |
|---|----------|--------|---------|
| 1 | **ContentTask не поддерживает блог** | Нет slug, SEO-полей, featured_image. Platform enum: только telegram/vk/youtube/instagram | Расширить модель: добавить `platform="wordpress"`, новые поля в metadata_json ИЛИ отдельная таблица `blog_posts` |
| 2 | **Publisher не знает WordPress** | `publisher.py:45-50` возвращает "unsupported" для неизвестных платформ | Добавить `_publish_wordpress()` метод + WordPress REST API клиент |
| 3 | **Нет агентной оркестрации** | BaseAgent — stateless, нет пайплайнов. Агенты не общаются | Добавить `WorkflowDAG` / `AgentPipeline` класс в `agents/orchestrator.py` |
| 4 | **12 агентов vs 3 существующих** | ТЗ требует 12 специализированных агентов | 9 новых наследников BaseAgent (минимальные изменения, 3 метода на агент) |
| 5 | **Next.js — scaffold без SEO** | Нет ISR, meta tags, schema.org, sitemap, динамических маршрутов | Добавить `/blog/*` роуты с полным SEO-стеком |

### Средние конфликты

| # | Конфликт | Решение |
|---|----------|---------|
| 6 | **Нет Google Sheets интеграции** | Новый сервис `google_sheets_sync.py` + Celery Beat polling |
| 7 | **Нет генерации изображений** | Новый сервис `image_generator.py` + S3 upload (MinIO есть) |
| 8 | **Perplexity API не интегрирован** | Добавить как tool для Research-агентов (аналог Qdrant RAG) |
| 9 | **Нет выделенного SEO worker** | Добавить `celery-worker-seo` в docker-compose.yml (тот же image, очереди seo+sheets) |
| 10 | **WordPress не в инфраструктуре** | Внешний сервис ИЛИ добавить WP + MySQL в compose |

### Без конфликтов (безопасно добавлять)

- Новые AI агенты — просто наследуют BaseAgent
- Blog API роутер — новый файл, не трогает существующие
- Sitemap/robots.txt — новые route handlers в Next.js
- Schema.org markup — компоненты фронтенда
- Author box — расширение User model (новые nullable поля)
- FAQ Schema — генерация JSON-LD в агенте Support

---

## 4. Маппинг 12 агентов ТЗ на BaseAgent

### Существующие агенты (переиспользование)

| Агент ТЗ | Существующий | Действие |
|----------|-------------|----------|
| Agent Marketer (№10) | `MarketerAgent` | Расширить prompt для SEO-контекста, добавить методы для Soft/Hard offer |
| — | `AnalystAgent` | Оставить как есть (конкурентный анализ) |
| — | `SalesAgent` | Интегрировать в report_generator (уже запланировано в Phase 6.2) |

### Новые агенты (9 штук)

| # | Агент | Класс | Модель | RAG | Температура | Назначение |
|---|-------|-------|--------|-----|-------------|-----------|
| 1 | Chief Investigator | `InvestigatorAgent` | Sonnet + Perplexity | Да (30 рез.) | 0.3 | Разведка трендов и фактов |
| 2 | Architect | `ArchitectAgent` | Sonnet | Да (15 рез.) | 0.0 | JSON Blueprint статьи |
| 3 | Research Manager | `ResearchManagerAgent` | Sonnet + Perplexity | Да (20 рез.) | 0.1 | Batch-поиск фактов |
| 4 | Journalist | `JournalistAgent` | Sonnet | Нет | 0.7 | H1, Intro, Conclusion |
| 5 | Writer | `WriterAgent` | Sonnet | Нет | 0.7 | Текст разделов |
| 6 | Editor (Humanizer) | `EditorAgent` | Sonnet | Нет | 0.95 | Humanization, стиль |
| 7 | Structurer | `StructurerAgent` | Sonnet | Нет | 0.3 | Таблицы, списки, цитаты |
| 8 | ArtDirector | `ArtDirectorAgent` | Haiku | Нет | 0.5 | Промпты для картинок |
| 9 | SEO Spec | `SEOSpecAgent` | Haiku | Нет | 0.2 | Meta, Schema, Tags |

### Необходимые изменения в BaseAgent

```python
# 1. Добавить AgentConfig для per-agent настроек
@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.7
    rag_enabled: bool = True
    rag_limit: int = 15
    output_format: str = "text"  # "text" | "json" | "html"

# 2. Добавить AgentOrchestrator для пайплайнов
class AgentOrchestrator:
    async def execute_pipeline(
        self,
        steps: list[dict],  # [{agent, input, depends_on}]
        context: dict
    ) -> dict[str, AgentResult]:
        """Execute agents in DAG order with dependency injection."""

# 3. Добавить Perplexity как дополнительный tool
class PerplexityTool:
    async def search(self, query: str, domain_filter: list[str]) -> str:
        """External factual search via Perplexity API."""
```

---

## 5. Новые модели данных (Alembic миграция)

```python
# backend/app/models/blog_post.py
class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)

    # Контент
    title = Column(String(500), nullable=False)
    slug = Column(String(200), nullable=False)
    body_html = Column(Text, nullable=False)
    excerpt = Column(String(500))

    # SEO
    meta_title = Column(String(70))
    meta_description = Column(String(170))
    seo_keywords = Column(JSONB, default=list)
    canonical_url = Column(String(500))

    # Медиа
    featured_image_url = Column(String(500))
    featured_image_alt = Column(String(300))

    # Таксономия
    category_id = Column(UUID, ForeignKey("blog_categories.id"))
    tags = Column(JSONB, default=list)

    # Метрики
    word_count = Column(Integer, default=0)
    reading_time_minutes = Column(Integer, default=0)

    # Schema.org
    schema_article = Column(JSONB)   # BlogPosting schema
    schema_faq = Column(JSONB)       # FAQPage schema
    schema_breadcrumb = Column(JSONB) # BreadcrumbList schema

    # WordPress sync
    wp_post_id = Column(Integer, nullable=True)
    wp_url = Column(String(500), nullable=True)

    # Workflow
    status = Column(String(50), default="draft")  # draft/review/published
    published_at = Column(DateTime(timezone=True))

    # Аудит
    ai_score = Column(Float)         # AI detection %
    seo_score = Column(Float)        # SEO checklist %
    generation_metadata = Column(JSONB)  # Все данные workflow

    # Индексы
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_blog_posts_user_slug"),
        Index("ix_blog_posts_status", "status"),
        Index("ix_blog_posts_published_at", "published_at"),
    )

class BlogCategory(Base):
    __tablename__ = "blog_categories"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False)
    description = Column(Text)
    wp_id = Column(Integer)  # ID в WordPress
```

---

## 6. Новые сервисы

### 6.1 WordPress Publisher
```
backend/app/services/wordpress_publisher.py
- publish_post(blog_post) → wp_post_id, wp_url
- update_post(blog_post)
- upload_media(image_url) → media_id
- create_category(name, slug) → category_id
- Uses: WordPress REST API + Application Passwords
```

### 6.2 Image Generator
```
backend/app/services/image_generator.py
- generate_from_prompt(prompt, ref_url, model) → image_url
- upload_to_s3(image_bytes) → s3_url
- Supports: Replicate (Flux), Kie.ai, fallback placeholder
```

### 6.3 SEO Content Pipeline
```
backend/app/services/seo_pipeline.py
- class SEOContentPipeline:
    - generate_article(keyword, settings) → BlogPost
    - Uses AgentOrchestrator with 12-agent DAG
    - Phases: Investigate → Plan → Research → Write → Edit → Publish
```

### 6.4 Google Sheets Sync
```
backend/app/services/google_sheets_sync.py
- read_conveyor(spreadsheet_id) → list[dict]
- update_status(row, status)
- write_to_published(post_data)
```

### 6.5 Perplexity Research Tool
```
backend/app/services/perplexity_client.py
- search(query, domain_filter) → {content, citations}
- Uses: Perplexity API (sonar-pro model)
```

---

## 7. Celery Workflow Engine (замена N8N)

### Почему Celery вместо N8N
N8N требует отдельный Docker-контейнер и внешнюю зависимость, которая не может быть развёрнута
в текущей среде. Celery chain/chord/group предоставляет DAG-подобное выполнение пайплайнов
с полным контролем из Python, без новых инфраструктурных зависимостей.

### Docker Compose дополнение
```yaml
celery-worker-seo:
  build:
    context: .
    dockerfile: infra/docker/Dockerfile.backend
  command: celery -A app.workers.celery_app worker --loglevel=info -Q seo,sheets -c 3
  restart: unless-stopped
  env_file: .env
  depends_on:
    postgres: { condition: service_healthy }
    redis: { condition: service_healthy }
  volumes:
    - ./backend:/app/backend
```

### Маппинг 7+1 Workflows → Celery Tasks

| WF # | Название | Celery Primitive | Задачи |
|------|----------|-----------------|--------|
| 0 | MASTER | Celery Beat poll (5 мин) | `poll_google_sheets` → dispatch chain |
| 1 | BRAIN | `chain()` | `brain_investigate → brain_architect → brain_validate` |
| 2 | HOOK | `chord(group(), merge)` | `group(hook_journalist, hook_art_director) → hook_merge` |
| 3 | BODY | `chord(group(), collect)` | `group(body_write_section * N) → body_collect` |
| 4 | ASSEMBLY | `chain()` | `assembly_merge` (EditorAgent + SEOSpecAgent) |
| 5 | PUBLISHER | `chain()` | `publish_to_wordpress` (WP REST API + ISR revalidation) |
| 6 | INDEXER | `group()` | `group(submit_google_indexnow, submit_yandex_webmaster)` |
| 7 | IMAGE GEN | `chord(group(), inject)` | `group(generate_single_image * N) → inject_images_into_html` |

### Полный pipeline (Python DAG)
```python
from celery import chain, chord, group

seo_article_pipeline = chain(
    # WF1 BRAIN — sequential
    brain_investigate.s(wf_run_id, keyword, settings),
    brain_architect.s(),
    brain_validate.s(),

    # WF2 HOOK — parallel journalist + art_director, then merge
    chord(
        group(hook_journalist.s(), hook_art_director.s()),
        hook_merge.s()
    ),

    # WF3 BODY — dynamic fan-out per section (inside body_fan_out)
    body_fan_out.s(),  # internally creates chord(group(sections), body_collect)

    # WF4 ASSEMBLY — merge all + final edit + SEO meta
    assembly_merge.s(),

    # WF7 IMAGE GEN — parallel image generation + inject into HTML
    assembly_with_images.s(),

    # WF5 PUBLISHER — WordPress publish + ISR revalidation
    publish_to_wordpress.s(),

    # WF6 INDEXER — Google IndexNow + Yandex Webmaster
    submit_indexing.s(),
)
```

### Новые модели для трекинга (замена N8N execution history)

```python
# backend/app/models/workflow_run.py
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey("users.id"), nullable=False)
    workflow_type = Column(String(50), nullable=False)      # "seo_article", "image_gen"
    status = Column(String(30), default="pending")           # pending/running/completed/failed/cancelled
    trigger_source = Column(String(50), nullable=False)     # "google_sheets", "api", "manual"
    input_data = Column(JSONB, nullable=False)
    output_data = Column(JSONB)
    blog_post_id = Column(UUID, ForeignKey("blog_posts.id"), nullable=True)
    celery_task_id = Column(String(255))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

class WorkflowStepLog(Base):
    __tablename__ = "workflow_step_logs"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    workflow_run_id = Column(UUID, ForeignKey("workflow_runs.id", ondelete="CASCADE"))
    step_name = Column(String(100), nullable=False)          # "brain.investigate"
    step_order = Column(Integer, nullable=False)
    status = Column(String(30), default="pending")
    agent_name = Column(String(50))
    celery_task_id = Column(String(255))
    input_summary = Column(JSONB)
    output_summary = Column(JSONB)
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
```

### WorkflowEngine (управление пайплайнами)
```python
# backend/app/services/workflow_engine.py
class WorkflowEngine:
    """Manages SEO pipeline lifecycle — replaces N8N orchestration."""

    async def start_seo_pipeline(self, user_id, keyword, settings) -> UUID:
        """Create WorkflowRun, dispatch Celery chain."""

    async def get_status(self, wf_run_id) -> WorkflowStatus:
        """Query WorkflowRun + steps, compute progress %."""

    async def cancel(self, wf_run_id) -> bool:
        """Revoke Celery task, mark cancelled."""

    async def retry_failed(self, wf_run_id) -> UUID:
        """Clone input, re-dispatch from failed step."""
```

### Real-time статус (замена N8N UI)
- **Redis pub/sub** канал `workflow:{run_id}:status` — каждый шаг публикует обновления
- **SSE endpoint** `GET /api/v1/workflows/{id}/stream` — фронтенд подписывается на поток
- **Workflow API** `GET /api/v1/workflows/{id}/status` — polling fallback
- **Google Sheets** обновляется автоматически (status → "processing" → "published")

### Workflow API Router
```
POST   /api/v1/workflows/start           — запуск pipeline
GET    /api/v1/workflows/                 — список runs (с фильтрами)
GET    /api/v1/workflows/{id}/status      — текущий статус + прогресс
GET    /api/v1/workflows/{id}/stream      — SSE real-time поток
GET    /api/v1/workflows/{id}/logs        — лог шагов
POST   /api/v1/workflows/{id}/cancel      — отмена
POST   /api/v1/workflows/{id}/retry       — повторный запуск
GET    /api/v1/workflows/stats            — агрегированная статистика
```

### Google Sheets Polling (замена N8N trigger)
```python
# Celery Beat schedule entry
"poll-google-sheets": {
    "task": "app.workers.sheets_tasks.poll_google_sheets",
    "schedule": 300.0,   # каждые 5 минут
    "options": {"queue": "sheets"},
}

# Redis distributed lock для дедупликации
# Lock key: "sheets:poll:lock", TTL: 270s
```

---

## 8. Next.js SEO Blog (новые файлы)

```
frontend/src/app/
├── blog/
│   ├── layout.tsx              # Blog layout с навигацией
│   ├── page.tsx                # Список постов (ISR 3600s)
│   ├── [slug]/
│   │   └── page.tsx            # Динамическая страница поста (ISR 60s)
│   ├── category/
│   │   └── [slug]/
│   │       └── page.tsx        # Посты по категории
│   ├── sitemap.xml/
│   │   └── route.ts            # Динамический sitemap
│   └── feed.xml/
│       └── route.ts            # RSS feed
├── components/
│   ├── blog/
│   │   ├── ArticleSchema.tsx   # JSON-LD Schema.org
│   │   ├── Breadcrumb.tsx      # Хлебные крошки
│   │   ├── TableOfContents.tsx # Содержание
│   │   ├── AuthorBox.tsx       # Карточка автора
│   │   ├── FAQBlock.tsx        # FAQ с schema
│   │   ├── RelatedPosts.tsx    # Похожие статьи
│   │   └── BlogCard.tsx        # Карточка статьи
│   └── seo/
│       └── SEOHead.tsx         # Dynamic meta tags
└── lib/
    ├── blog-api.ts             # API клиент для блога
    └── schema-org.ts           # Schema generators
```

### ISR Стратегия
- Главная блога `/blog` — revalidate каждый час (3600s)
- Страница поста `/blog/[slug]` — revalidate каждую минуту (60s)
- Категории — revalidate каждый день (86400s)
- On-demand revalidation через API при публикации

---

## 9. Порядок реализации (Phases)

### Phase 10: Фундамент Кибер SEO&GEO (2-3 недели)

```
10.1 Модели данных
├── BlogPost model + миграция Alembic
├── BlogCategory model + миграция
├── Расширить User (author_bio, author_photo_url)
└── Индексы и constraints

10.2 Агентная инфраструктура
├── AgentConfig dataclass
├── AgentOrchestrator (WorkflowDAG)
├── PerplexityTool (API клиент)
└── 9 новых агентов (наследники BaseAgent)

10.3 WordPress Publisher
├── wordpress_publisher.py (REST API клиент)
├── Интеграция в PublisherService (platform="wordpress")
└── Тесты
```

### Phase 11: SEO Content Pipeline (2-3 недели)

```
11.1 SEO Pipeline сервис
├── seo_pipeline.py (мастер-оркестратор)
├── WF1 Brain (Investigator + Architect + Validator)
├── WF2 Hook (Journalist + ArtDirector)
├── WF3 Body Loop (Writer + Editor + Structurer)
├── WF4 Assembly (Conclusion + FAQ + Author)
└── WF5 Publisher (WordPress + revalidation)

11.2 Image Generation
├── image_generator.py (Replicate/Kie.ai API)
├── S3 upload через MinIO
└── Alt-text генерация через ArtDirector

11.3 Blog API Router
├── CRUD для BlogPost
├── Категории и теги
├── Поиск (fulltext + Qdrant semantic)
└── Метрики (views, reading time)
```

### Phase 12: SEO Frontend (2-3 недели)

```
12.1 Blog Pages
├── /blog — список постов с пагинацией
├── /blog/[slug] — страница поста с ISR
├── /blog/category/[slug] — категории
└── Адаптивный дизайн (mobile-first)

12.2 SEO Components
├── Schema.org (Article, FAQ, Breadcrumb)
├── Dynamic meta tags (title, description, OG)
├── Sitemap.xml генератор
├── robots.txt
├── Breadcrumbs навигация
└── Table of Contents

12.3 UX Components
├── AuthorBox
├── RelatedPosts (Qdrant similarity)
├── FAQBlock с аккордеоном
├── ShareButtons
└── ReadingProgress bar
```

### Phase 13: Google Sheets + Workflow автоматизация (1-2 недели)

```
13.1 WorkflowEngine + модели трекинга
├── WorkflowRun + WorkflowStepLog модели (Alembic миграция)
├── WorkflowEngine сервис (start/status/cancel/retry)
├── workflow_callbacks.py (step logging + Redis pub/sub)
└── Celery task routes (seo + sheets queues)

13.2 Google Sheets интеграция
├── google_sheets_sync.py (gspread + service account)
├── CONVEYOR лист (очередь задач)
├── PUBLISHED лист (архив)
├── SETTINGS лист (настройки)
├── Celery Beat polling (каждые 5 мин)
└── Redis distributed lock для дедупликации

13.3 Workflow API Router + SSE
├── /api/v1/workflows/ (start, status, cancel, retry, logs)
├── SSE endpoint для real-time статуса
├── Pydantic schemas
└── Auth + rate limiting

13.4 Celery SEO Worker
├── Добавить celery-worker-seo в docker-compose.yml
├── Очереди: seo + sheets (изоляция от default worker)
└── Concurrency: 3 (ограничение Claude API нагрузки)
```

### Phase 14: Качество и мониторинг (1 неделя)

```
14.1 Content Quality Checks
├── AI Detection score (Agent Editor)
├── SEO Checklist автоматический
├── Schema.org валидация
├── PageSpeed мониторинг
└── Yoast-like scoring в pipeline

14.2 Индексация
├── Google IndexNow API
├── Yandex Webmaster API
├── Search Console интеграция
└── Мониторинг позиций (опционально)
```

---

## 10. Зависимости между новым ТЗ и текущим ROADMAP

```
Существующий ROADMAP          Кибер SEO&GEO
─────────────────────          ─────────────
Phase 6.1 Instagram Parser     (независим)
Phase 6.2 SalesAgent           (независим)
Phase 6.3-6.6 Dashboard ──────► Phase 12 Blog использует те же компоненты
Phase 7.1 Trends ─────────────► Phase 11 может использовать тренды для статей
Phase 7.2 Sentiment ──────────► Phase 11 Editor может использовать sentiment
Phase 8.2 Notifications ──────► Phase 13 WorkflowEngine может отправлять уведомления
Phase 9.1 Teams ──────────────► Blog посты привязаны к user_id (нужен organization_id позже)
```

### Рекомендуемый общий порядок:
1. **Phase 6** (пробелы) — 6.1, 6.2 (быстрые wins)
2. **Phase 10** (фундамент SEO) — модели + агенты + WordPress
3. **Phase 6.3-6.6** + **Phase 12** (фронтенд) — объединить Dashboard и Blog
4. **Phase 11** (SEO Pipeline) — конвейер статей
5. **Phase 13** (Workflow Engine + Google Sheets) — автоматизация
6. **Phase 7-9** (расширенная аналитика, teams)
7. **Phase 14** (качество) — финальная полировка

---

## 11. Новые ENV переменные

```env
# WordPress
WP_API_URL=https://api.example.com/wp-json/wp/v2
WP_USERNAME=admin
WP_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
WP_GRAPHQL_URL=https://api.example.com/graphql

# Perplexity API
PERPLEXITY_API_KEY=pplx-xxxx

# Image Generation
REPLICATE_API_TOKEN=r8_xxxx
KIE_AI_API_KEY=xxx
IMAGE_MODEL=flux-schnell

# Workflow Engine
SEO_PIPELINE_MAX_CONCURRENT=3
SEO_PIPELINE_SECTION_TIMEOUT=120
SEO_PIPELINE_TOTAL_TIMEOUT=600

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON=path/to/credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=xxx

# SEO
SEMRUSH_API_KEY=xxx  # опционально
DATAFORSEO_LOGIN=xxx  # опционально
DATAFORSEO_PASSWORD=xxx
SITE_DOMAIN=https://example.com
```

---

## 12. Оценка рисков

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Конфликт с Phase 6 Dashboard | Средняя | Среднее | Разделить: Dashboard = /dashboard, Blog = /blog |
| WordPress downtime | Низкая | Высокое | Fallback: хранить HTML в PostgreSQL, WP как mirror |
| Celery chain breaks mid-pipeline | Средняя | Среднее | `link_error` на каждой задаче, partial completion для body sections, WorkflowRun статус tracking |
| Claude API rate limits (12 агентов) | Высокая | Высокое | Batch запросы, Haiku для простых агентов, кэширование |
| Image generation latency | Высокая | Низкое | Async pipeline, placeholder images, WF7 с retry |
| Google Sheets API limits | Низкая | Среднее | Кэширование, batch reads, polling не чаще 5 мин |
| Миграция БД ломает существующее | Низкая | Высокое | Новые таблицы (blog_posts), не трогаем content_tasks |

---

## 13. Критерии приёмки (Definition of Done)

### MVP Кибер SEO&GEO:
- [ ] 12 агентов работают через AgentOrchestrator
- [ ] SEO Pipeline генерирует статью за 2-5 минут
- [ ] WordPress публикация через REST API
- [ ] Next.js отображает статью с ISR (< 60 сек)
- [ ] Schema.org: 0 ошибок в validator.schema.org
- [ ] PageSpeed: Mobile ≥ 90, Desktop ≥ 95
- [ ] Google Sheets: CONVEYOR → PUBLISHED автоматически
- [ ] Тестовая статья: ≥ 2000 слов, структурированная, читабельная
