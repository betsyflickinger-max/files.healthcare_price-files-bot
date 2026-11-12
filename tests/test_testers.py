import os, sys, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import testers

A, B, C = "a" * 64, "b" * 64, "c" * 64
JS = 'x\nconst TESTERS = {"%s": "mom", "%s": "rick"};\nconst MAGIC = {"%s": "mark"};\ny' % (A, B, C)


def names(js):
    _, t = testers._read(js)
    return t


def test_add():
    js, n = testers.edit_js(JS, "add", "Sarah ", "d" * 64)
    assert n == 3 and names(js)["d" * 64] == "sarah"
    assert 'const MAGIC = {"%s": "mark"}' % C in js and js.startswith("x\n") and js.endswith("\ny")
    assert testers.check(js, "add", "sarah", "d" * 64)


def test_add_existing_name_stops():
    with pytest.raises(SystemExit):
        testers.edit_js(JS, "add", "mom", "d" * 64)


def test_change_replaces_old_password():
    js, n = testers.edit_js(JS, "change", "mom", "d" * 64)
    t = names(js)
    assert n == 2 and A not in t and t["d" * 64] == "mom"
    assert testers.check(js, "change", "mom", "d" * 64)


def test_remove():
    js, n = testers.edit_js(JS, "remove", "rick")
    assert n == 1 and "rick" not in names(js).values()
    assert testers.check(js, "remove", "rick")


def test_bad_hash_and_unknown_name_stop():
    for args in [("add", "sam", "password"), ("change", "nobody", "d" * 64), ("remove", "nobody", ""), ("drop", "mom", "")]:
        with pytest.raises(SystemExit):
            testers.edit_js(JS, *args)
