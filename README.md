# Транскрибатор

Веб-приложение для транскрибации аудио и видео: загрузка → извлечение аудиодорожки → распознавание речи с таймкодами → автоматическая сводка → чат по содержанию → история обработок → админка.

Контекст проекта, глоссарий и архитектурные решения — в [CONTEXT.md](CONTEXT.md) и [docs/spec.md](docs/spec.md).

## Содержание

- [Локальный запуск для разработки](#локальный-запуск-для-разработки)
- [Получение ключей](#получение-ключей)
- [Развёртывание в проде](#развёртывание-в-проде)
- [Смена модели LLM](#смена-модели-llm)
- [Переключение режима распознавания](#переключение-режима-распознавания)
- [Ретеншн](#ретеншн)
- [Бэкап и восстановление базы](#бэкап-и-восстановление-базы)
- [Первый администратор](#первый-администратор)
- [Диагностика](#диагностика)

## Локальный запуск для разработки

Понадобится Docker и Docker Compose (входит в Docker Desktop на Windows/macOS; на Linux — пакет `docker-compose-plugin`).

```bash
git clone <адрес репозитория>
cd Транскрибатор
cp .env.example .env
```

Откройте `.env` и заполните хотя бы `JWT_SECRET_KEY` (любая случайная строка) и `ADMIN_EMAIL`/`ADMIN_PASSWORD` — под этими данными создастся первый Администратор. Остальные ключи (S3, SpeechKit, AI Gateway, SMTP, Telegram) можно оставить пустыми — соответствующие функции просто не будут работать, без выпадения ошибок в остальном приложении (см. [«Получение ключей»](#получение-ключей)).

```bash
docker compose up -d --build
```

- Веб-интерфейс: http://localhost:3000
- API: http://localhost:8001

Первый запуск создаёт таблицы в базе автоматически. При добавлении новых полей/таблиц в будущих версиях локальную базу нужно будет пересоздать: `docker compose down -v && docker compose up -d --build`.

## Получение ключей

### Timeweb S3

Хранилище исходных медиафайлов.

1. Зайдите в панель Timeweb Cloud → «Облачное хранилище» → создайте бакет S3 (регион `ru-1`, если не нужен другой).
2. В настройках бакета создайте пару ключей доступа (Access Key / Secret Key).
3. Заполните в `.env`:
   ```
   S3_ENDPOINT_URL=https://s3.timeweb.cloud
   S3_ACCESS_KEY=<ваш access key>
   S3_SECRET_KEY=<ваш secret key>
   S3_BUCKET=<имя бакета>
   S3_REGION=ru-1
   ```
4. У бакета должен быть включён CORS, разрешающий `PUT`-запросы и заголовок `ETag` в ответе (`Access-Control-Expose-Headers: ETag`) — без этого не будет работать прямая multipart-загрузка из браузера.
5. **CORS проверяет origin браузера**, а не только методы/заголовки — `AllowedOrigins` должен содержать точный публичный адрес фронтенда (например, `https://transcribator.example.com`), а не только `http://localhost:3000` для разработки. Промах здесь незаметен на бэкенде и в curl — браузер молча блокирует запрос ещё до отправки, а `XMLHttpRequest` в веб-консоли показывает это неотличимо от обрыва сети («сеть оборвалась при загрузке части»). При каждой смене адреса фронтенда (новый IP, новый домен, переход на HTTPS) — обновляйте `AllowedOrigins` бакета.
6. **`AllowedHeaders` тоже нужен, если запрос шлёт заголовок `Content-Type`.** Загрузка Записи (без `Content-Type` в подписи URL) через это не спотыкается, а вот загрузка скриншота к тикету поддержки (см. раздел «Тикеты и автофикс») шлёт `Content-Type: image/png` — браузер делает preflight `OPTIONS`, и без `AllowedHeaders: ["*"]` (или явно `["content-type"]`) в правиле CORS этот preflight падает с той же на вид «сетевой» ошибкой. Итоговый минимальный пример правила:
   ```json
   {
     "AllowedMethods": ["GET", "PUT", "HEAD"],
     "AllowedOrigins": ["https://transcribator.example.com"],
     "AllowedHeaders": ["*"],
     "ExposeHeaders": ["ETag"]
   }
   ```

### Яндекс SpeechKit

Распознавание речи.

1. Зарегистрируйтесь в [Yandex Cloud](https://console.cloud.yandex.ru/), привяжите платёжный аккаунт (карта или СБП).
2. Создайте каталог (folder) — его ID понадобится ниже.
3. В каталоге включите сервис SpeechKit и создайте сервисный аккаунт с ролью `ai.speechkit-stt.user`.
4. Создайте API-ключ для этого сервисного аккаунта.
5. Заполните в `.env`:
   ```
   YANDEX_API_KEY=<API-ключ сервисного аккаунта>
   YANDEX_FOLDER_ID=<ID каталога>
   ```

### Timeweb AI Gateway

Сводка Записи и ответы в Диалоге.

1. В панели Timeweb Cloud откройте «AI Gateway», создайте шлюз.
2. Скопируйте ключ доступа шлюза.
3. Заполните в `.env`:
   ```
   TIMEWEB_AI_GATEWAY_KEY=<ключ шлюза>
   TIMEWEB_AI_GATEWAY_URL=https://api.timeweb.ai/v1
   TIMEWEB_AI_GATEWAY_MODEL=gpt-4o-mini
   ```
   Актуальные тарифы на модели уточняйте в панели управления — часть цен публикуется только там.

### SMTP

Письма о готовности Записи.

Подойдёт любой почтовый ящик с доступом по SMTP (Yandex Mail, Mail.ru, corporate SMTP и т.д.). Обычно нужен отдельный пароль приложения, а не пароль от самого ящика — уточните в настройках безопасности вашего почтового сервиса.

```
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=<пароль приложения>
SMTP_FROM=notifications@example.com
```

Если оставить `SMTP_HOST` пустым, письма не отправляются, а попытка пишется в логи ошибок — остальная обработка Записи не прерывается.

### Telegram-бот

Опциональное дублирование уведомлений в Telegram.

1. Напишите [@BotFather](https://t.me/BotFather) в Telegram, выполните `/newbot`, следуйте инструкциям.
2. Получите токен вида `123456:ABC-DEF...` и имя бота (без `@`).
3. Заполните в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=<токен>
   TELEGRAM_BOT_USERNAME=<имя бота без @>
   ```
4. В проде дополнительно зарегистрируйте вебхук у Telegram, указав `TELEGRAM_WEBHOOK_SECRET` (см. ниже, раздел «Развёртывание в проде»).

Если `TELEGRAM_BOT_TOKEN` не задан, привязка Telegram в личном кабинете просто не сработает — email-уведомления продолжают работать как обычно.

## Развёртывание в проде

Инструкция для чистой машины (проверено на Ubuntu-подобном образе Timeweb Cloud, Москва — см. [ADR 0001](docs/adr/0001-timeweb-russia-hosting.md)).

### 1. Подготовка сервера

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# перелогиньтесь, чтобы группа docker применилась
```

### 2. DNS

Заведите два A-записи, указывающие на IP сервера:

- `transcribator.example.com` — основной сайт
- `api.transcribator.example.com` — API

Дождитесь распространения DNS (`dig transcribator.example.com` должен показывать IP сервера) — Caddy получает TLS-сертификаты Let's Encrypt автоматически при первом обращении, и без правильного DNS выпуск сертификата не пройдёт.

**Нет своего домена?** Let's Encrypt не выдаёт сертификаты на голый IP, но можно получить рабочий HTTPS без регистрации домена через [sslip.io](https://sslip.io) — публичный DNS-сервис, который резолвит `<любая-метка>.<IP-через-дефисы>.sslip.io` прямо в этот IP. Для сервера `5.42.98.64`:

```
DOMAIN=5-42-98-64.sslip.io
API_DOMAIN=api.5-42-98-64.sslip.io
```

Настройки DNS заводить не нужно — резолвинг уже работает. Подходит как временное решение или для тестового окружения; при переходе на свой домен позже меняются только эти две строки и origin в CORS S3-бакета (см. выше).

### 3. Клонирование и настройка

```bash
git clone <адрес репозитория>
cd Транскрибатор
cp .env.example .env
```

Заполните `.env` полностью — все ключи из раздела [«Получение ключей»](#получение-ключей) выше, плюс:

```
FRONTEND_BASE_URL=https://transcribator.example.com
DOMAIN=transcribator.example.com
API_DOMAIN=api.transcribator.example.com
CADDY_ACME_EMAIL=<ваш email — на него Let's Encrypt пришлёт уведомление, если сертификат не продлится>
```

`JWT_SECRET_KEY` и `POSTGRES_PASSWORD` должны быть случайными строками, отличными от значений по умолчанию:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy слушает 80 и 443, сам получает и продлевает сертификаты, проксирует `DOMAIN` на фронтенд и `API_DOMAIN` на API. Ни один из остальных сервисов (Postgres, Redis, api, worker, web) не публикует порты наружу — только через Caddy.

Проверить, что всё поднялось:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f caddy
```

Первый выпуск сертификата занимает от нескольких секунд до пары минут.

### 5. Telegram-вебхук (если используете Telegram-бота)

После того как API доступен по `https://api.transcribator.example.com`, зарегистрируйте вебхук:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://api.transcribator.example.com/telegram/webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET из .env>"
```

### Обновление после изменений в коде

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Если менялась схема базы данных (новые поля/таблицы) — миграций в проекте нет, схема применяется через `Base.metadata.create_all()` при старте API, что безопасно добавляет новые таблицы/поля к уже существующим без потери данных. Опасно за пределами `create_all()` (переименование или удаление колонки) в проекте пока не происходило; если понадобится — потребуется ручная миграция через `psql`.

## Смена модели LLM

Одна строка в `.env`, без правки кода:

```
TIMEWEB_AI_GATEWAY_MODEL=<название модели из каталога Timeweb AI Gateway>
```

Затем:

```bash
docker compose -f docker-compose.prod.yml up -d api worker
```

(В локальной разработке — `docker compose up -d api worker`.)

## Переключение режима распознавания

`DEFAULT_PROCESSING_MODE` в `.env` — `fast` («сейчас», ~30 минут, полная цена SpeechKit) или `deferred` («в фоне», до 24 часов, чтверть цены). Значение читается фронтендом через `GET /config`, поэтому смена варианта по умолчанию — тоже одна строка в `.env`, без правки кода:

```
DEFAULT_PROCESSING_MODE=fast
```

Пользователь всегда может переопределить режим при загрузке конкретного файла — эта настройка влияет только на то, какой вариант предвыбран.

## Ретеншн

Два срока хранения, оба настраиваются в `.env` без правки кода:

```
MEDIA_RETENTION_DAYS=30   # исходный медиафайл удаляется из S3
DATA_RETENTION_DAYS=180   # Запись целиком (включая Транскрипт, Сводку, Диалог)
```

Ночная джоба в воркере (по расписанию, 03:00 UTC) удаляет то, что старше срока. Изменения вступают в силу со следующего запуска джобы — перезапуск сервисов не требуется.

## Бэкап и восстановление базы

Все данные приложения (кроме медиафайлов, которые лежат в S3) — в Postgres. Команды ниже используют `POSTGRES_USER`/`POSTGRES_DB` по умолчанию (`transcribator`) — если меняли их в `.env`, подставьте свои значения.

### Бэкап

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U transcribator transcribator | gzip > backup-$(date +%Y%m%d).sql.gz
```

Рекомендуется добавить эту команду в cron сервера (например, ежедневно) и хранить бэкапы вне сервера — на S3 или локальной машине.

### Восстановление

```bash
gunzip -c backup-20260101.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U transcribator transcribator
```

Перед восстановлением на уже работающий инстанс остановите `api` и `worker`, чтобы не писать в базу параллельно с восстановлением:

```bash
docker compose -f docker-compose.prod.yml stop api worker
# восстановление
docker compose -f docker-compose.prod.yml start api worker
```

Восстановление базы не восстанавливает объекты в S3 — если нужен полный откат, S3-бакет нужно бэкапить отдельно (например, через `aws s3 sync` с S3-совместимым клиентом, настроенным на `S3_ENDPOINT_URL`).

## Первый администратор

При старте API, если пользователь с email из `ADMIN_EMAIL` ещё не существует, он создаётся автоматически с ролью `admin` и паролем из `ADMIN_PASSWORD`. Это единственный способ получить первого Администратора — обычная регистрация всегда создаёт пользователя со статусом «ожидает одобрения», а одобрять новых пользователей может только уже существующий Администратор.

Дальнейших администраторов можно назначать только напрямую в базе (роль `admin` у `users`) — интерфейс управления ролями не входит в MVP.

## Диагностика

```bash
# логи конкретного сервиса
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f worker

# логи ошибок обработки Записей — также доступны в интерфейсе
# администратора (/admin/errors) с фильтром по уровню и Записи
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U transcribator -d transcribator -c "select * from error_logs order by created_at desc limit 20;"
```

Если сертификат Caddy не выпускается — проверьте, что DNS уже указывает на сервер и порты 80/443 открыты во внешнем файрволе (у облачного провайдера, не только `ufw`/`iptables` на самой машине).
