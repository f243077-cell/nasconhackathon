from app.canonical import canonical, lots_key, sign


def test_appendix_a_vector_1_signature():
    payload = {"team_id": "t1", "event_type": "goal"}
    assert canonical(payload) == '{"event_type":"goal","team_id":"t1"}'
    assert sign("evt-1", payload, salt="demo-salt") == "972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"


def test_appendix_a_vector_2_lots_order():
    keys = {t: lots_key(42, "lg-1", t) for t in ("t1", "t2", "t3")}
    assert keys["t1"] == "0613316991ce0ac31e88d6003e3ff4d5e21bb072ac5f81b42c0cdc6598453293"
    assert sorted(keys, key=keys.get) == ["t1", "t3", "t2"]


def test_canonical_keeps_non_ascii_and_array_order():
    assert canonical({"b": [3, 1], "a": "é"}) == '{"a":"é","b":[3,1]}'


def test_salt_is_not_trimmed():
    assert sign("x", {}, salt="s ") != sign("x", {}, salt="s")
