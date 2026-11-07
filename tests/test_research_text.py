"""Preview-only site text: inserted once, sources linked, wording rules kept. Run: python -m pytest tests/"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site"))
import research_text as RT  # noqa: E402


def test_methodology():
    page = "<html><body><main><h1>Methodology</h1></main></body></html>"
    once = RT.methodology(page)
    assert RT.methodology(once) == once                                    # safe to run twice
    for t in ("These are contracted rates, not what was paid. Many listed rates may never be used.",
              "91.8%", "PMC12631121", "EO-25-21-Memo", "about 21% of claim dollars", "prices track hospital size and market power",
              "researchexperts.utmb.edu", "PMC11010067"):
        assert t in once, t
    assert "ghost" not in once.lower()
    assert once.index("RESEARCH-NOV7") < once.index("</main>")


def test_employer_framing():
    page = ('<h1>Look up an employer&#x27;s health plan</h1><p class="lede">Insurers publish an index.</p>'
            "<div class=\"pf\"><b>See its rates in the Dallas–Fort Worth Price Finder:</b></div>")
    out = RT.employer_plans(page)
    assert "<h1>Which network files your plan uses</h1>" in out and "does not show what the plan pays" in out
    assert "See its rates" not in out and RT.employer_plans(out) == out
    ins = RT.insurer_page("<p>1,234 Texas employers&#x27; health plans are named in this insurer&#x27;s price-file indexes.</p>")
    assert "which network files each plan uses, not what the plan pays" in ins


def test_strip_unranked():
    rows = [dict(measure_id="overall_star", measure_name="Hospital overall star rating", value="", unit="stars",
                 national_value="national: ...", cms_comparison="", data_period="", fewer_measures_reported="yes",
                 not_rated_reason="not rated. CMS footnote 16: too few measures", source_title="Hospital General Information",
                 source_link="https://data.cms.gov/provider-data/dataset/xubh-q36u", cms_release="2026-07-22")]
    s = RT.quality_strip(rows)
    assert "not rated" in s and "CMS footnote 16" in s and "Fewer measures reported" in s
    assert "Not a score and not a ranking" in s and "rank" not in s.replace("not a ranking", "")
    page = "<main><section><h2>Medicare&#x27;s quality rating</h2><p>x</p></section><section><h2>Price file</h2></section></main>"
    out = RT.add_strip(page, s)
    assert out.index("quality-strip") < out.index("Price file") and RT.add_strip(out, s) == out
