from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import cache, db
from .matching import UnitError, classify_recipes, have_enough, normalise, to_base

app = FastAPI(title="pantry-matcher")


@app.get("/health")
def health():
    out = {"status": "ok", "postgres": False, "redis": False}
    try:
        db.query("SELECT 1")
        out["postgres"] = True
    except Exception as e:
        out["pg_error"] = str(e)
    try:
        cache.client().ping()
        out["redis"] = True
    except Exception as e:
        out["redis_error"] = str(e)
    return out if out["postgres"] and out["redis"] else JSONResponse(out, status_code=503)


def _recipes():
    rows = db.query(
        "SELECT r.id, r.name,"
        " json_object_agg(i.name, ri.base_qty) AS needs"
        " FROM recipes r JOIN recipe_items ri ON ri.recipe_id=r.id"
        " JOIN ingredients i ON i.id=ri.ingredient_id GROUP BY r.id ORDER BY r.id")
    return [{"id": r["id"], "name": r["name"],
             "needs": {normalise(k): float(v) for k, v in r["needs"].items()}} for r in rows]


@app.get("/recipes")
def recipes():
    return {"recipes": _recipes()}


@app.get("/pantry/{user}")
def pantry(user: str):
    rows = db.query("SELECT i.name, p.base_qty FROM pantry p"
                    " JOIN ingredients i ON i.id=p.ingredient_id WHERE p.user_name=%s", (user,))
    return {"user": user, "items": {r["name"]: float(r["base_qty"]) for r in rows}}


@app.put("/pantry/{user}")
def set_pantry(user: str, payload: dict = Body(...)):
    items = payload.get("items") or []
    db.query("DELETE FROM pantry WHERE user_name=%s", (user,), fetch=False)
    stored = {}
    with db.connect() as conn, conn.cursor() as cur:
        for it in items:
            name = normalise(it.get("name"))
            if not name:
                continue
            try:
                qty = to_base(it.get("qty", it.get("grams", 0)), it.get("unit", "g"),
                              bool(it.get("liquid")))
            except UnitError as e:
                raise HTTPException(400, str(e))
            cur.execute("INSERT INTO ingredients (name) VALUES (%s)"
                        " ON CONFLICT (name) DO NOTHING", (name,))
            cur.execute("SELECT id FROM ingredients WHERE name=%s", (name,))
            iid = cur.fetchone()["id"]
            cur.execute("INSERT INTO pantry (user_name, ingredient_id, base_qty)"
                        " VALUES (%s,%s,%s)", (user, iid, qty))
            stored[name] = qty
    cache.drop(f"cook:{user}")
    return {"user": user, "items": stored}


@app.get("/pantry/{user}/cookable")
def cookable(user: str):
    hit = cache.get_json(f"cook:{user}")
    if hit:
        return {**hit, "cached": True}
    have = pantry(user)["items"]
    out = classify_recipes(have, _recipes())
    cache.set_json(f"cook:{user}", out, ttl=120)
    return {**out, "cached": False}


@app.get("/recipes/{rid}/shopping/{user}")
def shopping(rid: int, user: str):
    recipe = next((r for r in _recipes() if r["id"] == rid), None)
    if not recipe:
        raise HTTPException(404, "no such recipe")
    ok, missing = have_enough(pantry(user)["items"], recipe["needs"])
    return {"recipe": recipe["name"], "can_cook": ok, "shopping_list": missing}


@app.delete("/pantry/{user}/{ingredient}")
def remove_from_pantry(user: str, ingredient: str):
    name = normalise(ingredient)
    rows = db.query(
        "DELETE FROM pantry p USING ingredients i"
        " WHERE p.ingredient_id=i.id AND p.user_name=%s AND i.name=%s"
        " RETURNING i.name",
        (user, name))
    if not rows:
        raise HTTPException(404, "ingredient not in pantry")
    cache.drop(f"cook:{user}")
    return {"user": user, "removed": name}
