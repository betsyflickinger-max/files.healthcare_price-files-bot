"""Research tab patch (Nov 13, 2026; Research Desk v1, story 1.1)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import control_research as cr

PAGE = """<html><body>
<div class="tabs" id="tabs" role="tablist"><button type="button" role="tab" data-tab="changes" aria-selected="false">Changes</button>""" + cr.GH_BTN + cr.PLAN_BTN + """</div>
  <div class="page" id="pg-changes" hidden></div>
  """ + cr.GH_PAGE + """
  <div class="page" id="pg-plan" hidden></div>
<script>
  function show(which) {
    """ + cr.GH_SHOW + """
    dash.setLink(which === 'changes' ? 'changes' : """ + cr.GH_HASH + """);
  }
</script>
</body></html>"""


def page(tmp_path, text=PAGE):
    p = tmp_path / "site" / "control"
    p.mkdir(parents=True)
    (p / "index.html").write_text(text, encoding="utf-8")
    return str(tmp_path), p / "index.html"


def test_adds_tab_once(tmp_path):
    d, f = page(tmp_path)
    assert cr.patch(d) is True
    s = f.read_text(encoding="utf-8")
    assert s.index(cr.GH_BTN) < s.index(cr.BTN) < s.index(cr.PLAN_BTN)
    assert s.count('id="pg-research"') == 1 and s.count("window.RDTAB.show()") == 1
    assert "which === 'github' ? 'github' : which === 'research' ? 'research' : 'top'" in s
    assert s.count(cr.END) == 1 and s.index(cr.END) < s.index("</body>")
    assert cr.patch(d) is False   # second run changes nothing
    assert f.read_text(encoding="utf-8") == s


def test_new_block_replaces_old_copy(tmp_path):
    d, f = page(tmp_path)
    cr.patch(d)
    s = f.read_text(encoding="utf-8")
    a, b = s.index(cr.START), s.index(cr.END) + len(cr.END)
    f.write_text(s[:a] + cr.START + " old -->" + cr.END + s[b:], encoding="utf-8")
    assert cr.patch(d) is True
    s2 = f.read_text(encoding="utf-8")
    assert s2 == s and s2.count(cr.START) == 1


def test_missing_anchor_is_reported_not_fatal(tmp_path, capsys):
    d, f = page(tmp_path, PAGE.replace(cr.GH_SHOW, ""))
    cr.patch(d)
    s = f.read_text(encoding="utf-8")
    assert "window.RDTAB.show()" not in s.split(cr.START)[0]   # that step skipped
    assert 'data-tab="research"' in s                          # the others still went in
    assert "a Research tab step was skipped" in capsys.readouterr().out


def test_no_control_page(tmp_path):
    assert cr.patch(str(tmp_path)) is False
