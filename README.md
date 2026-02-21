# Генератор палитры коллекции

Минимальный сервис на FastAPI для генерации палитры 5-7 цветов с ролями, проверками в LAB/LCH, подбором Pantone-аналогов (через подключаемый провайдер) и экспортом в PDF A4.

## Что добавлено для публикации в интернет

- Продакшен-конфиг через переменные окружения (`APP_ENV`, `TRUSTED_HOSTS`, `CORS_ALLOW_ORIGINS`, пути к БД).
- Запуск через `gunicorn + uvicorn workers` (подходит для Render/Railway/Fly.io/VPS).
- Контейнеризация: `Dockerfile` + `.dockerignore`.
- `Procfile` для платформ с веб-процессом.
- `.env.example` с готовыми параметрами.
- Исправлены зависимости для продакшена (`Pillow`, `gunicorn`).

## Локальный запуск

```bash
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
.venv\\Scripts\\uvicorn app.main:app --reload
```

Открыть: `http://127.0.0.1:8000/`

## Продакшен-запуск (без Docker)

```bash
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
copy .env .env
```

Минимально настройте в `.env`:
- `TRUSTED_HOSTS=your-domain.com,www.your-domain.com`
- `CORS_ALLOW_ORIGINS=https://your-domain.com`

Запуск:

```bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --workers 2 --timeout 120 --bind 0.0.0.0:%PORT%
```

## Запуск в Docker

Сборка:

```bash
docker build -t pantone-tcx .
```

Запуск:

```bash
docker run --rm -p 8000:8000 \
  -e APP_ENV=production \
  -e TRUSTED_HOSTS=localhost,127.0.0.1 \
  -e CORS_ALLOW_ORIGINS=http://localhost:8000 \
  pantone-tcx
```

## Рекомендуемая публикация

1. Развернуть на Render/Railway/Fly.io (или VPS).
2. Указать стартовую команду из `Procfile`.
3. Прописать переменные окружения из `.env.example`.
4. Настроить домен и HTTPS.
5. Для постоянных данных подключить том и задать `PALETTE_DB_PATH` в каталог тома.

## API

- `POST /api/palette/generate`
- `GET /api/palette/{id}`
- `GET /api/palette/{id}/pdf`
- `POST /api/photo/tcx` (multipart: `image`, необязательный `count`)
- `POST /api/tcx/match-color` (JSON: `hex`, необязательный `k`)
- `POST /api/donate/create-payment` (создание платежа для виджета ЮKassa)
- `GET /api/tcx/{code}` (детальная карточка TCX по коду)
- `GET /health`

### Ключевой цвет

Можно передавать:
- устаревший формат: `key_color: "#D26C31"` (HEX)
- расширенно: `key_color_mode` + `key_color_value`
  - `key_color_role`: `accent` (по умолчанию) или `base`
  - `seed` (опционально): фиксирует повторяемую генерацию; если не передан, палитра случайная на каждый запуск
  - `hex`: `#D26C31`
  - `rgb`: `210,108,49`
  - `cmyk`: `0,49,77,18`
  - `lab`: `58,25,45`
  - `tcx_code`: `17-0836`
  - `tcx_name`: `Ecru Olive`

## Тесты

```bash
.venv\\Scripts\\pytest -q
```

## ЮKassa виджет

Для блока пожертвований через виджет заполните в `.env`:

- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `YOOKASSA_RETURN_URL`

После этого внизу страниц будет работать оплата через встроенный виджет ЮKassa.
