import pytest

from app.matching import (
    UnitError,
    classify_recipes,
    have_enough,
    normalise,
    to_base,
)


# ---------- normalise ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Flour", "flour"),
        ("  Sugar  ", "sugar"),
        ("eggs", "egg"),
        ("EGGS", "egg"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalise(raw, expected):
    assert normalise(raw) == expected


# ---------- to_base: conversions ----------


def test_grams_stay_grams():
    assert to_base(250, "g") == 250.0


def test_kilograms_to_grams():
    assert to_base(1.5, "kg") == 1500.0


def test_cup_of_solid_is_120_grams():
    assert to_base(2, "cup") == 240.0


def test_cup_of_liquid_is_240_ml():
    assert to_base(1, "cup", liquid=True) == 240.0


def test_cup_differs_for_solid_and_liquid():
    assert to_base(1, "cup") != to_base(1, "cup", liquid=True)


def test_spoons_solid():
    assert to_base(2, "tbsp") == 30.0
    assert to_base(3, "tsp") == 15.0


def test_spoons_liquid():
    assert to_base(2, "tbsp", liquid=True) == 30.0
    assert to_base(3, "tsp", liquid=True) == 15.0


def test_litres_to_ml():
    assert to_base(0.5, "l", liquid=True) == 500.0
    assert to_base(2, "litre", liquid=True) == 2000.0


def test_pieces_to_grams():
    assert to_base(3, "piece") == 150.0


def test_unit_is_case_and_space_insensitive():
    assert to_base(1, " KG ") == 1000.0


def test_quantity_can_be_a_numeric_string():
    assert to_base("250", "g") == 250.0


def test_zero_quantity_is_allowed():
    assert to_base(0, "g") == 0.0


# ---------- to_base: errors ----------


def test_unit_error_is_a_value_error():
    assert issubclass(UnitError, ValueError)


def test_unknown_unit_raises():
    with pytest.raises(UnitError, match="unknown unit"):
        to_base(1, "bucket")


def test_negative_quantity_raises():
    with pytest.raises(UnitError, match="negative"):
        to_base(-1, "g")


def test_non_numeric_quantity_raises():
    with pytest.raises(UnitError, match="not a quantity"):
        to_base("abc", "g")


def test_missing_quantity_raises():
    with pytest.raises(UnitError, match="not a quantity"):
        to_base(None, "g")


def test_mass_unit_is_not_valid_for_liquids():
    with pytest.raises(UnitError):
        to_base(1, "g", liquid=True)


def test_volume_unit_is_not_valid_for_solids():
    with pytest.raises(UnitError):
        to_base(1, "ml")


# ---------- the hard part: cups vs grams ----------


def test_two_cups_of_flour_equals_240_grams():
    assert to_base(2, "cup") == to_base(240, "g")


def test_cups_in_recipe_compare_with_grams_in_pantry():
    pantry = {"flour": to_base(500, "g")}
    needed = {"flour": to_base(2, "cup")}
    ok, missing = have_enough(pantry, needed)
    assert ok is True
    assert missing == {}


def test_cups_in_recipe_with_too_little_in_pantry():
    pantry = {"flour": to_base(200, "g")}
    needed = {"flour": to_base(2, "cup")}
    ok, missing = have_enough(pantry, needed)
    assert ok is False
    assert missing == {"flour": 40.0}


# ---------- have_enough ----------


def test_enough_when_pantry_covers_everything():
    ok, missing = have_enough(
        {"flour": 500.0, "egg": 200.0},
        {"flour": 240.0, "egg": 100.0},
    )
    assert ok is True
    assert missing == {}


def test_exact_amount_is_enough():
    ok, missing = have_enough({"flour": 240.0}, {"flour": 240.0})
    assert ok is True
    assert missing == {}


def test_shortfall_is_reported():
    ok, missing = have_enough({"flour": 100.0}, {"flour": 240.0})
    assert ok is False
    assert missing == {"flour": 140.0}


def test_absent_ingredient_is_fully_missing():
    ok, missing = have_enough({}, {"egg": 100.0})
    assert ok is False
    assert missing == {"egg": 100.0}


def test_needed_names_are_normalised():
    ok, missing = have_enough({"egg": 150.0}, {"Eggs": 100.0})
    assert ok is True
    assert missing == {}


def test_multiple_missing_ingredients():
    ok, missing = have_enough(
        {"flour": 100.0},
        {"flour": 240.0, "sugar": 30.0},
    )
    assert ok is False
    assert missing == {"flour": 140.0, "sugar": 30.0}


def test_shortfall_is_rounded_to_two_places():
    ok, missing = have_enough({"flour": 0.1}, {"flour": 0.3})
    assert ok is False
    assert missing == {"flour": 0.2}


def test_substitute_covers_missing_ingredient():
    ok, missing = have_enough({"oil": 50.0}, {"butter": 30.0})
    assert ok is True
    assert missing == {}


def test_substitutes_are_added_together():
    ok, missing = have_enough(
        {"oil": 20.0, "ghee": 15.0},
        {"butter": 30.0},
    )
    assert ok is True
    assert missing == {}


def test_substitute_that_is_not_enough():
    ok, missing = have_enough({"oil": 10.0}, {"butter": 30.0})
    assert ok is False
    assert missing == {"butter": 20.0}


def test_substitutes_can_be_switched_off():
    ok, missing = have_enough(
        {"oil": 50.0},
        {"butter": 30.0},
        allow_substitutes=False,
    )
    assert ok is False
    assert missing == {"butter": 30.0}


def test_milk_can_be_replaced_by_yoghurt():
    ok, missing = have_enough({"yoghurt": 300.0}, {"milk": 240.0})
    assert ok is True
    assert missing == {}


def test_ingredient_without_substitute_is_not_replaced():
    ok, missing = have_enough({"oil": 100.0}, {"egg": 100.0})
    assert ok is False
    assert missing == {"egg": 100.0}


# ---------- classify_recipes ----------

RECIPES = [
    {
        "id": 1,
        "name": "Pancakes",
        "needs": {"flour": 240.0, "sugar": 30.0, "egg": 100.0},
    },
    {
        "id": 2,
        "name": "Omelette",
        "needs": {"egg": 150.0, "onion": 50.0},
    },
    {
        "id": 3,
        "name": "Dal Rice",
        "needs": {"rice": 300.0, "dal": 200.0, "onion": 100.0},
    },
]


def names(entries):
    return [e["name"] for e in entries]


def test_classify_can_cook_now_is_sorted_by_name():
    pantry = {"flour": 500.0, "sugar": 100.0, "egg": 300.0, "onion": 200.0}
    result = classify_recipes(pantry, RECIPES)
    assert names(result["can_cook_now"]) == ["Omelette", "Pancakes"]
    assert result["need_one_more"] == []
    assert names(result["need_more"]) == ["Dal Rice"]


def test_classify_one_missing_ingredient():
    pantry = {"flour": 500.0, "sugar": 100.0, "egg": 300.0}
    result = classify_recipes(pantry, RECIPES)
    assert names(result["can_cook_now"]) == ["Pancakes"]
    assert result["need_one_more"] == [
        {"id": 2, "name": "Omelette", "missing": {"onion": 50.0}}
    ]
    assert names(result["need_more"]) == ["Dal Rice"]


def test_classify_empty_pantry_sorts_by_missing_count_then_name():
    result = classify_recipes({}, RECIPES)
    assert result["can_cook_now"] == []
    assert result["need_one_more"] == []
    assert names(result["need_more"]) == ["Omelette", "Dal Rice", "Pancakes"]


def test_classify_no_recipes():
    assert classify_recipes({}, []) == {
        "can_cook_now": [],
        "need_one_more": [],
        "need_more": [],
    }


def test_classify_recipe_with_no_needs_can_be_cooked():
    result = classify_recipes({}, [{"id": 9, "name": "Water", "needs": {}}])
    assert result["can_cook_now"] == [{"id": 9, "name": "Water", "missing": {}}]


def test_classify_uses_substitutes():
    recipes = [{"id": 5, "name": "Toast", "needs": {"butter": 30.0}}]
    result = classify_recipes({"oil": 50.0}, recipes)
    assert names(result["can_cook_now"]) == ["Toast"]
