# API

Базов адрес: `http://localhost:8000` локално или `https://<проект>.vercel.app` във Vercel.

Интерактивна документация, генерирана от кода: `/docs` (Swagger UI) и `/redoc`. Машинно четима схема: `/openapi.json`.

## Съдържание

- [GET /health](#get-health)
- [POST /predict](#post-predict)
- [GET /predict](#get-predict)
- [Формат на отговора](#формат-на-отговора)
- [Статуси на проверката](#статуси-на-проверката)
- [Грешки](#грешки)
- [Защита с API ключ](#защита-с-api-ключ)
- [Примери на JavaScript и Python](#примери-на-javascript-и-python)

---

## GET /health

Проверка дали услугата е жива и какво е включено.

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "model_loaded": true,
  "landmarks_known": 33543,
  "gemini_enabled": true,
  "gemini_models": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
}
```

`gemini_enabled: false` значи, че няма `GEMINI_API_KEY` или в `GEMINI_MODELS` няма нито един безплатен модел.

---

## POST /predict

Разпознава забележителност. Снимката се подава **или** като файл, **или** като URL.

Тялото е `multipart/form-data`:

| Поле | Тип | Задължително | Описание |
|---|---|---|---|
| `file` | файл | едно от двете | Снимка: jpg, png, webp, gif, bmp... До `MAX_UPLOAD_BYTES` (4 MB) |
| `url` | текст | едно от двете | URL към снимка. Може и в адреса: `/predict?url=...` |
| `top` | число 1–20 | не, 3 | Колко кандидата да има в `candidates` |
| `verify` | `auto` / `always` / `never` | не, `auto` | Кога да се пита Gemini (виж по-долу) |
| `lang` | код на език | не, `bg` | Език на `info`. Ако няма статия на този език, връща английската |

`url`, `verify` и `lang` може да са и в адреса (`?verify=always`). Ако има и файл, и URL, се ползва файлът.

**verify:**

- `auto`: Gemini се пита само когато локалният модел е несигурен (правилата са в [ARCHITECTURE.md](ARCHITECTURE.md#кога-се-вика-gemini)).
- `always`: Gemini проверява винаги. Харчи от дневния лимит.
- `never`: само локалният модел. Най-бързо.

Примери:

```bash
# файл
curl -F "file=@trevi.jpg" http://localhost:8000/predict

# URL в тялото
curl -F "url=https://example.com/trevi.jpg" http://localhost:8000/predict

# URL в адреса (например от Postman)
curl -X POST "http://localhost:8000/predict?url=https://example.com/trevi.jpg"

# всички параметри
curl -F "file=@trevi.jpg" -F "top=5" -F "verify=always" -F "lang=en" http://localhost:8000/predict
```

**Google Images линкове.** Линк като `https://www.google.com/imgres?...&imgurl=...` води до страница, не до снимка. API-то сам вади истинската снимка от `imgurl`. Работи и когато линкът е поставен некодиран в `?url=`.

---

## GET /predict

Същото, но само с URL. Удобно за браузър:

```
http://localhost:8000/predict?url=https://example.com/trevi.jpg&lang=bg&verify=auto&top=3
```

Ако URL-ът на снимката съдържа `&`, кодирай го (`encodeURIComponent` в JavaScript) или ползвай POST.

---

## Формат на отговора

```json
{
  "source": "trevi.jpg",
  "landmark": { ... },
  "info": { ... },
  "candidates": [ ... ],
  "verification": { ... }
}
```

### `source`

Името на качения файл или URL-ът на снимката (след разопаковане на Google Images линк).

### `landmark`: крайният отговор

| Поле | Тип | Описание |
|---|---|---|
| `name` | текст или `null` | Името на забележителността. `null`, ако Gemini каже, че на снимката няма забележителност |
| `score` | число или `null` | Оценката на локалния модел за това име (0–1). `null`, ако Gemini е дал име, което не е сред кандидатите |
| `source` | `local` / `gemini` / `local+gemini` | Кой е дал отговора. `local+gemini` = Gemini е потвърдил локалния модел |
| `confident` | `true` / `false` | Дали може да се вярва на отговора. `true` само ако два независими източника са съгласни (вж. таблицата със статусите). `false` при `disputed`, `error`, `unavailable` и при `corrected` / `no_landmark`, когато е отговорил само един модел на Gemini |

### `info`: информация за забележителността

Когато има информация:

| Поле | Описание |
|---|---|
| `found` | `true` |
| `title` | Заглавие на статията на поискания език |
| `summary` | Първите до 4 изречения от статията |
| `language` | Езикът на `title`/`summary`/`url` (може да е `en`, ако няма статия на поискания) |
| `url` | Линк към статията |
| `image` | Снимка от статията (до 640 px) или `null` |
| `coordinates` | `{"lat": ..., "lon": ...}` или `null` |
| `english_title`, `english_url` | Английската статия, винаги налична |
| `source` | `wikipedia` |

Когато няма:

```json
{ "found": false, "message": "Няма информация за тази забележителност" }
```

Възможни съобщения:

- `Няма информация за тази забележителност`: в Wikipedia няма подходяща статия.
- `Няма информация за тази забележителност (Wikipedia не отговори: ...)`: временен проблем, следващата заявка ще опита пак.
- `На снимката не е разпозната забележителност`: Gemini е казал, че няма забележителност.
- `Не е сигурно коя е забележителността, затова не се връща информация`: статус `disputed`.

### `candidates`: суровите предложения на локалния модел

Списък от `{"name": ..., "score": ...}`, подреден по оценка. Дължината се задава с `top`.

Оценката не е вероятност и сборът не е 1. Над ~0.85 обикновено е вярно, около 0.7 е несигурно.

### `verification`: какво е станало с проверката

| Поле | Описание |
|---|---|
| `needed` | Дали резултатът е пратен за проверка |
| `reasons` | Защо е сметнат за несигурен (празно, ако е сигурен) |
| `status` | Виж таблицата по-долу |
| `gemini` | Приетият отговор на Gemini или `null`: `model`, `landmark`, `wikipedia_title`, `matches_candidate`, `confidence` (`high`/`medium`/`low`), `reason` (на български) |
| `answers` | Всички отговори от Gemini моделите (същия формат), включително неприетите. Полезно при `disputed` |
| `agreement` | `all` = отговорилите модели са съгласни; `single` = отговорил е само един (другият е бил претоварен или с ниска увереност); `null`, ако няма приет отговор |
| `error` | Обяснение, ако Gemini не е помогнал |

## Статуси на проверката

| `status` | Значение | `landmark.source` | `confident` |
|---|---|---|---|
| `skipped` | Не е било нужно (или `verify=never`) | `local` | `true` (при `verify=never` и несигурен резултат: `false`) |
| `confirmed` | Gemini е съгласен с локалния модел | `local+gemini` | `true` |
| `corrected` | Gemini е дал друг отговор, може и извън кандидатите | `gemini` | `true`, ако двата модела са съгласни; `false`, ако е отговорил само един (`agreement: single`) |
| `no_landmark` | Gemini не вижда забележителност; `landmark.name` е `null` | `gemini` | като при `corrected` |
| `disputed` | Gemini моделите не са съгласни помежду си или не са сигурни (`confidence: low`); върнат е локалният резултат **без информация** | `local` | `false` |
| `unavailable` | Gemini не е настроен; върнат е локалният резултат | `local` | `false` |
| `error` | Лимит, претоварване (503/504), таймаут или друга грешка в Gemini; върнат е локалният резултат | `local` | `false` |

**Важно:** при `disputed`, `unavailable` и `error` API-то **не връща грешка**. Отговорът е 200 с локалния резултат, `landmark.confident` е `false`, а `verification.error` казва какво е станало.

Възможни съобщения в `verification.error`:

- `Безплатният лимит на Gemini е изчерпан за момента ...`: грешка 429, лимитът се нулира до 24 часа.
- `Gemini е претоварен в момента (грешка 503/504) ...`: временно претоварване от страна на Google. Опитай пак след малко.
- `Gemini моделите не са сигурни или не са съгласни помежду си ...`: статус `disputed`.
- `Gemini не отговори (TimeoutError) ...`: никой модел не е отговорил навреме.
- `Gemini не е настроен (няма GEMINI_API_KEY) ...`: статус `unavailable`.

## Грешки

Грешките са във формат `{"detail": "съобщение"}` (на български).

| HTTP код | Кога |
|---|---|
| 400 | Няма нито `file`, нито `url`; файлът не е снимка; URL-ът води до уеб страница; URL-ът не се тегли; URL към вътрешен адрес или нестандартен порт; грешен `lang` или `verify` |
| 401 | Зададен е `API_KEYS`, а `X-API-Key` липсва или е грешен |
| 413 | Снимката е твърде голяма (по размер или по резолюция над 100 мегапиксела) |
| 422 | Грешен тип на параметър, например `top=abc` или `top=50` |

## Защита с API ключ

Ако зададеш `API_KEYS=ключ1,ключ2`, всяка заявка към `/predict` трябва да има хедър:

```bash
curl -H "X-API-Key: ключ1" -F "file=@snimka.jpg" https://<проект>.vercel.app/predict
```

`/health` и `/docs` остават отворени. В `/docs` има бутон „Authorize“ за ключа.

Препоръчително е при публичен деплой, за да не изразходва някой друг безплатния лимит на Gemini.

## Примери на JavaScript и Python

JavaScript (браузър), файл от `<input type="file">`:

```js
const form = new FormData();
form.append("file", input.files[0]);
form.append("lang", "bg");
const res = await fetch("https://<проект>.vercel.app/predict", { method: "POST", body: form });
const data = await res.json();
console.log(data.landmark.name, data.info.summary);
```

JavaScript, URL:

```js
const url = "https://example.com/trevi.jpg";
const res = await fetch(`https://<проект>.vercel.app/predict?url=${encodeURIComponent(url)}`);
```

Python:

```python
import requests

with open("trevi.jpg", "rb") as f:
    r = requests.post("http://localhost:8000/predict", files={"file": f}, data={"lang": "bg"})
r.raise_for_status()
data = r.json()
print(data["landmark"]["name"], data["info"].get("summary"))
```
