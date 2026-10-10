# Pantry to Recipe Matcher

**Language:** Python (FastAPI) &nbsp;|&nbsp; **Needs:** Postgres + Redis

This is a **starter**. The application already works. Your job is everything
that gets it building, tested and running in CI.

---

## You do not need Python installed

You will build this into a container, and the container brings its own
Python 3.12. You are not being asked to extend the app — you are being asked
to ship it.

---

## 1. What this app needs

| | |
|---|---|
| **Runtime** | Python 3.12 |
| **Install dependencies** | `pip install -r requirements.txt` |
| **Start the app** | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| **Listens on** | port 8080, bound to `0.0.0.0` |
| **Environment variables** | `DATABASE_URL`, `REDIS_URL` |
| **Needs running first** | Postgres, Redis, and the migrations applied |

### What it does

Tell it what is in your kitchen. It shows what you can cook now, what you could cook with one more item, and builds a shopping list for a recipe you pick.

### Endpoints

```
GET  /health
GET  /recipes                     every recipe with its ingredients
GET  /pantry/{user}               what they have
PUT  /pantry/{user}               {"items":[{"name":"flour","grams":500}]}
GET  /pantry/{user}/cookable      can cook now / need one more
GET  /recipes/{id}/shopping/{user} what is missing, with quantities
```

`/health` reports Postgres and Redis **separately**. If it says
`postgres: false` the app started fine and your compose wiring is wrong —
do not go looking in the application code.

### Migrations

`migrations/` holds `.sql` files applied **in filename order** before the app
starts. They create the tables and insert sample data. A container running
`psql` over them in order is enough; you do not need a migration tool.

---

## 2. What you must write

| File | What it has to do |
|---|---|
| `Dockerfile` | Install dependencies **before** copying source, pin the base image, do not run as root. |
| `docker-compose.yml` | App + Postgres + Redis + a migration step, one `docker compose up`. |
| `.circleci/config.yml` | lint → unit tests → integration tests → secret scan → image build |
| Unit tests | For `app/matching.py`. No database, no network. |
| Integration tests | Against a real Postgres and Redis as CircleCI service containers. |

Then push your image to **your own Docker Hub account**, tagged `:1.0`.

### When it works

```bash
docker compose up --build
curl localhost:8080/health
```

```json
{"status":"ok","postgres":true,"redis":true}
```

---

## Where the marks are

`app/matching.py` is **pure logic** — plain functions over plain data, no
database and no HTTP. Start your tests there. Use pytest:
`pytest --cov=app --cov-report=term-missing`. Minimum 70%.



## Why Redis is here

Redis sets, used for exactly what they were designed for: intersect a pantry with each recipe's ingredients instead of doing it in SQL.

## The hard part

Units. 2 cups of flour and 250g of flour are the same ingredient, and students will treat them as two. Normalise to one base unit per ingredient type and test the conversions.

Write your answer in your README. It is worth more marks than the feature.

---

## Getting unstuck

| Symptom | Almost always |
|---|---|
| `/health` says `postgres: false` | Wrong hostname. In compose the host is the **service name**, not `localhost`. |
| Page will not load, logs fine | No `ports:` mapping, or bound to `127.0.0.1` not `0.0.0.0`. |
| `relation "..." does not exist` | Migrations did not run, or the app started before they finished. |
| Build takes minutes each time | `COPY . .` is above your dependency install. |
| CI cannot reach the database | In CircleCI service containers the host **is** `localhost` — opposite of compose. |


---

# My Submission

## How to run

```
docker compose up --build
curl localhost:8080/health
```

Expected: `{"status":"ok","postgres":true,"redis":true}`

Image on Docker Hub: `docker pull srilakshmi0212/pantry-matcher:1.0`

## The hard part: units

**The problem.** A recipe may ask for "2 cups of flour" while the pantry holds
"500 g of flour". If these are stored as they were typed, the matcher sees two
unrelated quantities and can never compare them.

**My approach: convert once, at the edge, to a single base unit.**

- Everything is converted to **grams** (solids) or **millilitres** (liquids)
  by `to_base()` in `app/matching.py`, using two lookup tables (`TO_GRAMS`, `TO_ML`).
- Conversion happens when a pantry is saved (`PUT /pantry/{user}`). The database
  only ever stores `base_qty`, so every comparison afterwards is plain number
  against number. `have_enough()` and `classify_recipes()` never see a unit.
- The same word can mean different amounts depending on the ingredient. A cup of
  flour is 120 g but a cup of milk is 240 ml. `to_base()` takes a `liquid` flag so
  that "cup" is never converted by one blanket rule.
- Bad input is rejected, not guessed. An unknown unit (`"bucket"`), a negative
  quantity, or a non-number raises `UnitError`, and the API returns HTTP 400.
- Ingredient names are normalised too (lower-case, trimmed, trailing "s" removed)
  so "Eggs" and "egg" are the same ingredient.
- Substitutes (butter ↔ oil/ghee, milk ↔ curd/yoghurt) are added together before
  deciding what is missing.

**Tests.** `tests/test_matching.py` checks every conversion, both meanings of
"cup", every error case, and the key scenario: 2 cups of flour in a recipe is
satisfied by 500 g in the pantry, and 200 g leaves a shortfall of exactly 40 g.

**Known limitations (what I would fix next).**

- `cup = 120 g` is the flour value. A cup of sugar or rice weighs more, so those
  would be slightly wrong. The proper fix is a density table per ingredient.
- The `liquid` flag is supplied by the caller. If a client sends milk without it,
  milk is stored in grams and will not match a recipe that stores it in ml. The
  proper fix is to store the base unit per ingredient in the database.
- Names are singularised with `rstrip("s")`, which would wrongly turn
  "molasses" into "molasse". A proper plural rule or an ingredient alias table
  would be better.
- `piece = 50 g` is a rough average for every item.

## Design notes

- In compose the database host is the service name `db`. In CircleCI service
  containers the host is `localhost`. The two files use different URLs for this reason.
- The `migrate` service applies `migrations/*.sql` in filename order and exits.
  The app only starts after it finishes successfully.
- Redis is used as a result cache for `/pantry/{user}/cookable` (120 s). Saving a
  pantry invalidates that user's cache key. The matching itself runs in Python,
  not with Redis sets.

## Tests

- Unit tests: `tests/test_matching.py` (no database, no network).
- Integration tests: `tests/test_integration.py` (real Postgres and Redis).
- Overall coverage: 100% (minimum required is 70%).