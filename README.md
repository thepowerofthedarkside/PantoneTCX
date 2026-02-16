# Генератор палитры коллекции

MVP-сервис на FastAPI для генерации палитры 5-7 цветов с ролями, проверками в LAB/LCH, подбором Pantone-аналогов (через подключаемый провайдер) и экспортом в PDF A4.

## Запуск

```bash
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
.venv\\Scripts\\uvicorn app.main:app --reload
```

Открыть: `http://127.0.0.1:8000/`

## API

- `POST /api/palette/generate`
- `GET /api/palette/{id}`
- `GET /api/palette/{id}/pdf`
- `POST /api/photo/tcx` (multipart: `image`, optional `count`)
- `POST /api/tcx/match-color` (JSON: `hex`, optional `k`)
- `GET /api/tcx/{code}` (детальная карточка TCX по коду)
- `GET /health`

### Ключевой цвет (новое)

Можно передавать:
- legacy: `key_color: "#D26C31"` (HEX)
- расширенно: `key_color_mode` + `key_color_value`
  - `key_color_role`: `accent` (по умолчанию) или `base`
  - `seed` (опционально): фиксирует повторяемую генерацию; если не передан, палитра случайная на каждый запуск
  - `hex`: `#D26C31`
  - `rgb`: `210,108,49`
  - `cmyk`: `0,49,77,18`
  - `lab`: `58,25,45`
  - `tcx_code`: `17-0836`
  - `tcx_name`: `Ecru Olive`

### Анализ фото в TCX

- UI: на главной странице блок "Определить цвета из фото (TCX)".
- UI: на главной странице блок "Пипетка: выбрать цвет на фото" для точечного выбора пикселя и `TCX top-3`.
- UI: каждый `TCX` код/название в результатах кликабелен и ведет на страницу `/tcx/{code}` с деталями и похожими цветами.
- API:
  - `POST /api/photo/tcx`
  - `Content-Type: multipart/form-data`
  - поля:
    - `image`: файл изображения
    - `count`: сколько доминирующих цветов извлечь (1..12, по умолчанию 6)
  - `POST /api/tcx/match-color`
  - `Content-Type: application/json`
  - body: `{ "hex": "#927B3C", "k": 3 }`

## Архитектура

- `app/services/color_math.py` - HEX/RGB/LAB/LCH/CMYK, DeltaE00
- `app/services/pantone_provider.py` - интерфейс `ColorLibraryProvider` и CSV-реализация
- `app/services/palette_service.py` - генерация ролей/цветов + проверки
- `app/services/storage.py` - sqlite-хранилище результатов
- `app/services/pdf_export.py` - PDF A4
- `app/routes.py` - API и UI маршруты

Справочник Pantone загружается из `data/pantone_stub.csv` и может быть заменен на лицензированный источник без изменения `palette_service`.

## Тесты

```bash
.venv\\Scripts\\pytest -q
```

