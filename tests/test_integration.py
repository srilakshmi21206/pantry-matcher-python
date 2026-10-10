
from app import cache, db


def put(client, user, items):
    return client.put(f"/pantry/{user}", json={"items": items})


def names(entries):
    return [e["name"] for e in entries]


# ---------- /health ----------


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": True, "redis": True}


def test_health_reports_redis_failure_separately(client, monkeypatch):
    class Broken:
        def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(cache, "client", lambda: Broken())
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 503
    assert body["postgres"] is True
    assert body["redis"] is False
    assert "redis down" in body["redis_error"]


def test_health_reports_postgres_failure_separately(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("postgres down")

    monkeypatch.setattr(db, "query", broken)
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 503
    assert body["postgres"] is False
    assert body["redis"] is True
    assert "postgres down" in body["pg_error"]


# ---------- /recipes ----------


def test_recipes_are_seeded_with_ingredients(client):
    recipes = client.get("/recipes").json()["recipes"]
    assert names(recipes) == ["Pancakes", "Dal Rice", "Omelette"]
    pancakes = recipes[0]
    assert pancakes["needs"] == {
        "flour": 240.0,
        "sugar": 30.0,
        "egg": 100.0,
        "butter": 30.0,
        "milk": 240.0,
    }


# ---------- PUT / GET pantry ----------


def test_new_user_has_an_empty_pantry(client):
    assert client.get("/pantry/nobody").json() == {"user": "nobody", "items": {}}


def test_put_pantry_in_grams_then_read_it_back(client):
    response = put(client, "srii", [{"name": "flour", "grams": 500}])
    assert response.status_code == 200
    assert response.json() == {"user": "srii", "items": {"flour": 500.0}}
    assert client.get("/pantry/srii").json()["items"] == {"flour": 500.0}


def test_put_pantry_converts_cups_of_flour_to_grams(client):
    put(client, "srii", [{"name": "flour", "qty": 2, "unit": "cup"}])
    assert client.get("/pantry/srii").json()["items"] == {"flour": 240.0}


def test_put_pantry_converts_cup_of_liquid_to_millilitres(client):
    put(client, "srii", [{"name": "milk", "qty": 1, "unit": "cup", "liquid": True}])
    assert client.get("/pantry/srii").json()["items"] == {"milk": 240.0}


def test_put_pantry_converts_kilograms(client):
    put(client, "srii", [{"name": "rice", "qty": 1.5, "unit": "kg"}])
    assert client.get("/pantry/srii").json()["items"] == {"rice": 1500.0}


def test_put_pantry_normalises_ingredient_names(client):
    put(client, "srii", [{"name": "  Eggs ", "grams": 200}])
    assert client.get("/pantry/srii").json()["items"] == {"egg": 200.0}


def test_put_pantry_skips_blank_names(client):
    put(client, "srii", [{"name": "   ", "grams": 5}])
    assert client.get("/pantry/srii").json()["items"] == {}


def test_put_pantry_replaces_the_previous_contents(client):
    put(client, "srii", [{"name": "flour", "grams": 500}])
    put(client, "srii", [{"name": "sugar", "grams": 100}])
    assert client.get("/pantry/srii").json()["items"] == {"sugar": 100.0}


def test_put_pantry_with_no_items_empties_it(client):
    put(client, "srii", [{"name": "flour", "grams": 500}])
    response = client.put("/pantry/srii", json={})
    assert response.json() == {"user": "srii", "items": {}}


def test_put_pantry_rejects_unknown_unit(client):
    response = put(client, "srii", [{"name": "flour", "qty": 1, "unit": "bucket"}])
    assert response.status_code == 400
    assert "unknown unit" in response.json()["detail"]


def test_put_pantry_rejects_negative_quantity(client):
    response = put(client, "srii", [{"name": "flour", "grams": -5}])
    assert response.status_code == 400


def test_pantries_are_separate_per_user(client):
    put(client, "asha", [{"name": "flour", "grams": 100}])
    put(client, "ravi", [{"name": "sugar", "grams": 50}])
    assert client.get("/pantry/asha").json()["items"] == {"flour": 100.0}
    assert client.get("/pantry/ravi").json()["items"] == {"sugar": 50.0}


# ---------- /pantry/{user}/cookable ----------


def test_cookable_with_empty_pantry(client):
    body = client.get("/pantry/srii/cookable").json()
    assert body["can_cook_now"] == []
    assert body["need_one_more"] == []
    assert names(body["need_more"]) == ["Omelette", "Dal Rice", "Pancakes"]
    assert body["cached"] is False


def test_cookable_finds_a_recipe_that_can_be_cooked_now(client):
    put(
        client,
        "srii",
        [
            {"name": "egg", "grams": 300},
            {"name": "onion", "grams": 100},
            {"name": "oil", "grams": 50},
        ],
    )
    body = client.get("/pantry/srii/cookable").json()
    assert names(body["can_cook_now"]) == ["Omelette"]


def test_cookable_finds_recipes_that_need_one_more_item(client):
    put(
        client,
        "srii",
        [
            {"name": "flour", "grams": 500},
            {"name": "sugar", "grams": 100},
            {"name": "egg", "grams": 300},
            {"name": "butter", "grams": 100},
        ],
    )
    body = client.get("/pantry/srii/cookable").json()
    assert body["can_cook_now"] == []
    assert names(body["need_one_more"]) == ["Omelette", "Pancakes"]
    pancakes = body["need_one_more"][1]
    assert pancakes["missing"] == {"milk": 240.0}
    assert names(body["need_more"]) == ["Dal Rice"]


def test_cookable_is_cached_then_invalidated_by_put(client):
    first = client.get("/pantry/srii/cookable").json()
    second = client.get("/pantry/srii/cookable").json()
    assert first["cached"] is False
    assert second["cached"] is True

    put(client, "srii", [{"name": "egg", "grams": 300}])
    third = client.get("/pantry/srii/cookable").json()
    assert third["cached"] is False


def test_cache_is_per_user(client):
    client.get("/pantry/asha/cookable")
    other = client.get("/pantry/ravi/cookable").json()
    assert other["cached"] is False


# ---------- /recipes/{id}/shopping/{user} ----------


def test_shopping_list_for_empty_pantry_is_the_whole_recipe(client):
    body = client.get("/recipes/1/shopping/srii").json()
    assert body["recipe"] == "Pancakes"
    assert body["can_cook"] is False
    assert body["shopping_list"] == {
        "flour": 240.0,
        "sugar": 30.0,
        "egg": 100.0,
        "butter": 30.0,
        "milk": 240.0,
    }


def test_shopping_list_shows_only_the_shortfall(client):
    put(client, "srii", [{"name": "flour", "grams": 100}])
    body = client.get("/recipes/1/shopping/srii").json()
    assert body["shopping_list"]["flour"] == 140.0


def test_shopping_list_is_empty_when_everything_is_in_the_pantry(client):
    put(
        client,
        "srii",
        [
            {"name": "egg", "grams": 300},
            {"name": "onion", "grams": 100},
            {"name": "oil", "grams": 50},
        ],
    )
    body = client.get("/recipes/3/shopping/srii").json()
    assert body["recipe"] == "Omelette"
    assert body["can_cook"] is True
    assert body["shopping_list"] == {}


def test_shopping_list_accepts_a_substitute(client):
    put(client, "srii", [{"name": "oil", "grams": 50}])
    body = client.get("/recipes/1/shopping/srii").json()
    assert "butter" not in body["shopping_list"]
    assert set(body["shopping_list"]) == {"flour", "sugar", "egg", "milk"}


def test_shopping_for_an_unknown_recipe_is_404(client):
    response = client.get("/recipes/999/shopping/srii")
    assert response.status_code == 404
    assert response.json()["detail"] == "no such recipe"


# ---------- cache and db helpers ----------


def test_cache_round_trip(client):
    cache.set_json("test:key", {"a": 1}, ttl=30)
    assert cache.get_json("test:key") == {"a": 1}


def test_cache_miss_returns_none(client):
    assert cache.get_json("test:missing") is None


def test_cache_drop_removes_keys(client):
    cache.set_json("test:one", {"a": 1})
    cache.set_json("test:two", {"b": 2})
    cache.drop("test:one", "test:two")
    assert cache.get_json("test:one") is None
    assert cache.get_json("test:two") is None


def test_cache_drop_with_no_keys_does_nothing(client):
    cache.drop()


def test_cache_drop_prefix_removes_only_matching_keys(client):
    cache.set_json("cook:a", {"x": 1})
    cache.set_json("cook:b", {"x": 2})
    cache.set_json("other:c", {"x": 3})
    cache.drop_prefix("cook:")
    assert cache.get_json("cook:a") is None
    assert cache.get_json("cook:b") is None
    assert cache.get_json("other:c") == {"x": 3}


def test_db_one_returns_a_row(database):
    assert db.one("SELECT 1 AS x") == {"x": 1}


def test_db_one_returns_none_when_there_are_no_rows(database):
    assert db.one("SELECT 1 AS x WHERE false") is None


def test_delete_removes_one_ingredient(client):
    put(client, "srii", [{"name": "flour", "grams": 500}, {"name": "sugar", "grams": 100}])
    response = client.delete("/pantry/srii/flour")
    assert response.status_code == 200
    assert response.json() == {"user": "srii", "removed": "flour"}
    assert client.get("/pantry/srii").json()["items"] == {"sugar": 100.0}


def test_delete_normalises_the_name(client):
    put(client, "srii", [{"name": "egg", "grams": 200}])
    assert client.delete("/pantry/srii/Eggs").status_code == 200
    assert client.get("/pantry/srii").json()["items"] == {}


def test_delete_missing_ingredient_is_404(client):
    response = client.delete("/pantry/srii/flour")
    assert response.status_code == 404
    assert response.json()["detail"] == "ingredient not in pantry"


def test_delete_only_affects_that_user(client):
    put(client, "asha", [{"name": "flour", "grams": 100}])
    put(client, "ravi", [{"name": "flour", "grams": 100}])
    client.delete("/pantry/asha/flour")
    assert client.get("/pantry/ravi").json()["items"] == {"flour": 100.0}


def test_delete_clears_the_cookable_cache(client):
    put(client, "srii", [{"name": "egg", "grams": 200}])
    client.get("/pantry/srii/cookable")
    assert client.get("/pantry/srii/cookable").json()["cached"] is True
    client.delete("/pantry/srii/egg")
    assert client.get("/pantry/srii/cookable").json()["cached"] is False
