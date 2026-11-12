# Деплой във Vercel

Проектът е готов за Vercel без допълнителни промени. Vercel открива FastAPI приложението в `app/main.py` автоматично.

## Какво е подготвено

| Файл | За какво е |
|---|---|
| `app/main.py` | Съдържа `app = FastAPI(...)`. Vercel търси точно това |
| `requirements.txt` | Само нужните за работа пакети, без torch и без TensorFlow |
| `.python-version` | Python 3.12 |
| `vercel.json` | `maxDuration: 120` секунди; тестове, документация и `.env` не влизат в пакета |
| `models/landmarks_classifier_europe_v1.tflite` | Моделът е в репото, за да няма теглене при всеки студен старт |

Размерът на функцията е около 200 MB, а лимитът на Vercel за Python е 500 MB. Основните части са LiteRT (~56 MB), моделът (48 MB), numpy (~31 MB), Pillow (~15 MB) и google-genai (~12 MB).

## Вариант 1: през сайта на Vercel (препоръчително)

1. Влез в [vercel.com](https://vercel.com) с GitHub акаунта си.
2. **Add New → Project** и избери репото `jivko25/AI-Landmark-Recognition` → **Import**.
3. Framework Preset ще се засече като **FastAPI**. Не променяй Build и Output настройките.
4. Отвори **Environment Variables** и добави:

   | Name | Value |
   |---|---|
   | `GEMINI_API_KEY` | ключът ти от AI Studio |
   | `API_KEYS` | (по желание, препоръчително) произволна тайна дума, напр. `moyat-tajen-kluch-123` |

   Останалите настройки имат разумни стойности по подразбиране (виж [README](../README.md#настройки)).
5. **Deploy**. След около 1–2 минути ще получиш адрес като `https://ai-landmark-recognition.vercel.app`.
6. Провери:

   ```bash
   curl https://<адрес>/health
   ```

   Трябва да видиш `"gemini_enabled": true`.

След това всеки push в `main` се деплойва автоматично, а pull request-ите получават отделен preview адрес.

## Вариант 2: с Vercel CLI

```bash
npm i -g vercel
cd AI-Landmark-Recognition
vercel login
vercel link                                   # свързва папката с проект във Vercel
vercel env add GEMINI_API_KEY production      # пита за стойността
vercel env add API_KEYS production            # по желание
vercel --prod
```

Локално, като във Vercel:

```bash
vercel dev
```

## Лимити на Vercel, които засягат API-то

| Лимит | Стойност | Какво значи тук |
|---|---|---|
| Размер на заявката | 4.5 MB | Качените снимки са до 4 MB (`MAX_UPLOAD_BYTES`). За по-големи снимки ползвай `url` |
| Време на изпълнение | до 300 s (Hobby), настроено на 120 s | Най-лошият случай (бавно теглене + 2 модела Gemini + Wikipedia) е под 60 s |
| Памет | 2 GB (Hobby) | Достатъчно: моделът е 48 MB, а снимките се смаляват преди обработка |
| Размер на функцията | 500 MB за Python | ~200 MB |

## Студен старт

Когато инстанцията е „заспала“, първата заявка зарежда библиотеките и модела (около 3 секунди) и е по-бавна. Следващите са бързи. Vercel Fluid compute държи инстанциите живи по-дълго, така че това рядко се усеща.

## Сигурност при публичен адрес

- **`API_KEYS`**: без него всеки, който знае адреса, може да вика API-то и да изразходва безплатния лимит на Gemini. Пари не се харчат, но лимитът може да свърши.
- **SSRF защитата** е включена винаги: URL към вътрешни адреси се отказва.
- **CORS**: по подразбиране всеки сайт може да вика API-то от браузър. Ако имаш собствен фронтенд, задай `CORS_ALLOW_ORIGINS=https://моят-сайт.com`.
- **Ключът на Gemini** стои само във Vercel Environment Variables, не в кода. `.env` е в `.gitignore`.
- **Ограничение на заявките:** за по-сериозна защита от злоупотреба добави правило в Vercel → Firewall → Rate Limiting (например 30 заявки в минута на IP).

## Проблеми

| Симптом | Причина и решение |
|---|---|
| `"gemini_enabled": false` | Липсва `GEMINI_API_KEY` в Environment Variables или не е направен нов deploy след добавянето ѝ (**Deployments → Redeploy**) |
| `413 FUNCTION_PAYLOAD_TOO_LARGE` | Снимката е над 4.5 MB. Смали я или подай `url` |
| `verification.status = "error"` с „лимит“ | Изчерпан е безплатният лимит на Gemini. Ще се нулира до 24 часа. Виж [ZERO_BUDGET.md](ZERO_BUDGET.md) |
| `504 FUNCTION_INVOCATION_TIMEOUT` | Много бавен сайт със снимката или Gemini. Свали `GEMINI_TIMEOUT_S` или `DOWNLOAD_TIMEOUT_S` |
| Build грешка за размера | Не трябва да се случва. Ако си добавил пакети, провери с `VERCEL_ANALYZE_BUILD_OUTPUT=1` кое е голямо |
| Логове | Vercel → проектът → **Logs** |
