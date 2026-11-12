# AI Landmark Recognition

REST API, което по снимка разпознава **европейска забележителност** и връща **информация за нея**. Работи с **нулев бюджет**: всичко, което ползва, е безплатно.

```
снимка ──► локален модел (Google Landmarks, ~33 500 места)
              │
              ├─ сигурен ─────────────────────────────┐
              │                                        ▼
              └─ несигурен ─► Gemini (безплатен) ─► Wikipedia ─► отговор
```

| Част | Какво прави | Цена |
|---|---|---|
| [Google Landmarks (Europe)](https://www.kaggle.com/models/google/landmarks) от Kaggle | Разпознава забележителността локално, без интернет | безплатно, Apache 2.0 |
| [Gemini API](https://ai.google.dev/gemini-api/docs/pricing) | Проверява и поправя несигурните отговори | само модели от безплатния план |
| [Wikipedia API](https://www.mediawiki.org/wiki/API:Main_page) | Описание, линк, снимка и координати | безплатно, без ключ |
| [Vercel](https://vercel.com) | Хостинг | Hobby планът е безплатен |

## Съдържание

- [Бърз старт](#бърз-старт)
- [Примерни заявки](#примерни-заявки)
- [Примерен отговор](#примерен-отговор)
- [Настройки](#настройки)
- [Тестове](#тестове)
- [Структура на проекта](#структура-на-проекта)
- [Ограничения](#ограничения)
- Подробно: [API](docs/API.md) · [Как работи](docs/ARCHITECTURE.md) · [Нулев бюджет и Gemini](docs/ZERO_BUDGET.md) · [Деплой във Vercel](docs/DEPLOYMENT.md)

## Бърз старт

Трябва Python 3.12 или по-нов.

```bash
git clone https://github.com/jivko25/AI-Landmark-Recognition.git
cd AI-Landmark-Recognition

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # и попълни GEMINI_API_KEY
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Интерактивна документация (може да качваш снимки от браузъра): http://localhost:8000/docs

Без `GEMINI_API_KEY` всичко работи, само проверката с Gemini е изключена.

## Примерни заявки

Прикачена снимка:

```bash
curl -F "file=@snimka.jpg" http://localhost:8000/predict
```

URL към снимка:

```bash
curl -F "url=https://example.com/snimka.jpg" http://localhost:8000/predict
curl "http://localhost:8000/predict?url=https://example.com/snimka.jpg"
```

Допълнителни параметри (и за двата начина):

```bash
curl -F "file=@snimka.jpg" -F "top=5" -F "verify=always" -F "lang=en" http://localhost:8000/predict
```

| Параметър | Стойности | По подразбиране | Значение |
|---|---|---|---|
| `top` | 1–20 | 3 | колко кандидата да се върнат в `candidates` |
| `verify` | `auto`, `always`, `never` | `auto` | кога да се пита Gemini |
| `lang` | `bg`, `en`, `de`, ... | `bg` | език на информацията; ако няма статия на този език, връща английската |

Пълно описание: [docs/API.md](docs/API.md).

## Примерен отговор

Снимка на фонтана Ди Треви от необичаен ъгъл. Локалният модел се колебае между „Palazzo Poli“ (сградата зад фонтана) и „Trevi Fountain“, Gemini поправя отговора, а информацията идва от българската Wikipedia:

```json
{
  "source": "https://i1.wp.com/time2travel.bg/wp-content/uploads/2020/02/Picture-4-min.png",
  "landmark": { "name": "Trevi Fountain", "score": 0.8228, "source": "gemini" },
  "info": {
    "found": true,
    "title": "Фонтан ди Треви",
    "summary": "Фонтанът ди Трѐви (на италиански: Fontana di Trevi) е един от най-известните фонтани в света ...",
    "language": "bg",
    "url": "https://bg.wikipedia.org/wiki/Фонтан_ди_Треви",
    "image": "https://upload.wikimedia.org/...",
    "coordinates": { "lat": 41.9008, "lon": 12.4831 },
    "english_title": "Trevi Fountain",
    "english_url": "https://en.wikipedia.org/wiki/Trevi_Fountain",
    "source": "wikipedia"
  },
  "candidates": [
    { "name": "Palazzo Poli", "score": 0.8466 },
    { "name": "Trevi Fountain", "score": 0.8228 },
    { "name": "Fountain of the Three Graces", "score": 0.7008 }
  ],
  "verification": {
    "needed": true,
    "reasons": [
      "най-високата оценка 0.847 е под 0.85",
      "първите два кандидата са твърде близо (0.847 и 0.823)"
    ],
    "status": "corrected",
    "gemini": {
      "model": "gemini-3.5-flash-lite",
      "landmark": "Trevi Fountain",
      "wikipedia_title": "Trevi Fountain",
      "matches_candidate": true,
      "confidence": "high",
      "reason": "На снимката се вижда известният Фонтан ди Треви в Рим."
    },
    "error": null
  }
}
```

Ако няма информация: `"info": {"found": false, "message": "Няма информация за тази забележителност"}`.

## Настройки

Всичко се задава с environment variables (локално в `.env`, във Vercel в Project Settings → Environment Variables). Пример: [.env.example](.env.example).

| Име | По подразбиране | Описание |
|---|---|---|
| `GEMINI_API_KEY` | — | Ключ от [Google AI Studio](https://aistudio.google.com/apikey). Без него Gemini е изключен. |
| `GEMINI_MODELS` | `gemini-3.5-flash-lite,gemini-3.1-flash-lite` | Модели по ред на опитване. **Платени модели се игнорират.** |
| `GEMINI_TIMEOUT_S` | `15` | Таймаут за всеки модел поотделно |
| `VERIFY_MIN_SCORE` | `0.85` | Под тази оценка резултатът е несигурен |
| `VERIFY_MIN_MARGIN` | `0.05` | Ако първите два кандидата са по-близо от това... |
| `VERIFY_SURE_SCORE` | `0.95` | ...и оценката е под това, резултатът е несигурен |
| `INFO_LANGUAGE` | `bg` | Език на информацията по подразбиране |
| `API_KEYS` | — | Ако е зададено (списък със запетаи), `/predict` иска хедър `X-API-Key` |
| `CORS_ALLOW_ORIGINS` | `*` | Кои сайтове могат да викат API-то от браузър |
| `MAX_UPLOAD_BYTES` | 4 MB | Максимален размер на качена снимка (Vercel спира всичко над 4.5 MB) |
| `MAX_DOWNLOAD_BYTES` | 15 MB | Максимален размер на снимка по URL |
| `DOWNLOAD_TIMEOUT_S` | `10` | Таймаут при теглене по URL |
| `WIKIPEDIA_TIMEOUT_S` | `8` | Таймаут към Wikipedia |
| `LANDMARK_MODEL_PATH` | `models/landmarks_classifier_europe_v1.tflite` | Път до модела |

## Тестове

```bash
pytest
```

41 теста, около 2 секунди. Gemini и Wikipedia са заменени с фалшиви обекти, така че тестовете не харчат безплатния лимит и не зависят от интернет. Истинският модел се зарежда и разпознава Айфеловата кула.

## Структура на проекта

```
app/
  main.py          FastAPI приложение и ендпойнти (Vercel го намира автоматично)
  pipeline.py      Последователността: локален модел → Gemini → Wikipedia
  recognizer.py    Локалният TFLite модел
  verifier.py      Gemini: кога се вика и самото повикване
  wiki.py          Информация от Wikipedia
  images.py        Качване и теглене на снимки (със защита от SSRF)
  schemas.py       Формат на отговорите (и на документацията в /docs)
  config.py        Настройки от environment variables
models/
  landmarks_classifier_europe_v1.tflite   Моделът от Kaggle (48 MB, етикетите са вградени)
tests/             pytest тестове
docs/              Подробна документация
vercel.json        Настройки за Vercel
.python-version    Python 3.12 за Vercel
```

## Ограничения

- **Само Европа.** Локалният модел знае европейски забележителности. Gemini може да познае и други, но само когато е викан.
- **Моделът не знае всичко.** Например Колизеумът и Нойшванщайн ги няма в списъка му. Тогава оценката обикновено е ниска, Gemini се включва и поправя.
- **Безплатният Gemini има лимити:** около 15 заявки в минута и 500 на ден за модел. При изчерпан лимит API-то връща локалния резултат и казва защо в `verification.error`. Подробно: [docs/ZERO_BUDGET.md](docs/ZERO_BUDGET.md).
- **Бавен понякога.** Безплатният Gemini отговаря за 2 до 15 секунди. Ако не отговори за 15 секунди, се пробва резервният модел, така че в най-лошия случай отговорът идва за около 30 секунди. Когато Gemini не е нужен, отговорът е под секунда.
- **Снимки до 4 MB при качване във Vercel.** По URL може и по-големи (до 15 MB).

## Лицензи

- Моделът Google Landmarks е под [Apache 2.0](https://www.kaggle.com/models/google/landmarks), виж [models/NOTICE](models/NOTICE).
- Текстовете от Wikipedia са под [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Отговорът винаги съдържа линк към статията.
