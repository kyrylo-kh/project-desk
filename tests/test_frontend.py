# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The browser code's pure parts (static/js/*.js and static/modules/*/render.js), run in Node.

Each test renders real API payloads from the Python side, in English and in Ukrainian, and checks the
HTML: the labels come from the locales, and everything from the files is escaped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from project_desk.desk import Desk
from project_desk.i18n import load_locale, plural_category

from support import ABOUT, ABOUT_BLOCK, DECISION, NODE_SKIP, dec, make_repo, node_eval, parked, qa

pytestmark = pytest.mark.skipif(NODE_SKIP is not None, reason=NODE_SKIP or "")

I18N = {"I": "js/i18n.js"}


def strings(lang: str) -> dict[str, Any]:
    return load_locale("en") | load_locale(lang)


def view(lang: str, **extra: str) -> str:
    """JS statements that build the render context `v` for a language (the data must carry `strings`)."""
    more = "".join(f", {k}: {json.dumps(v)}" for k, v in extra.items())
    return (
        f"const i = I.makeI18n(D.strings, {json.dumps(lang)});"
        f"const v = {{ i, cl: 'uk', lang: {json.dumps(lang)}, MOD: '⌘', SHIFT: '⇧', dir: 'decisions', command: 'desk'{more} }};"
    )


# --------------------------------------------------------------------------- i18n.js and util.js


def test_plural_categories_match_python() -> None:
    counts = [0, 1, 2, 3, 4, 5, 11, 12, 14, 21, 22, 25, 101, 111, 112, 1001]
    r = node_eval(
        I18N, {lang: f"D.map((n) => I.pluralCategory({json.dumps(lang)}, n))" for lang in ("en", "uk")}, counts
    )
    for lang in ("en", "uk"):
        assert r[lang] == [plural_category(lang, n) for n in counts], lang


def test_translate_escapes_params_but_not_the_template() -> None:
    data = {"strings": strings("uk")}
    r = node_eval(
        I18N,
        {
            "t": "i.t('dec.toast_answered', {id: 'D-1', choice: '<b>'})",
            "h": "i.h('dec.parked_line', {option: '<img src=x>'})",
            "raw": "i.h('plan.none_text', {file: I.html('<code>f</code>')})",
            "n": "[1, 3, 5].map((n) => i.n('qa.left', n))",
            "plural": "[1, 3, 5, 21].map((n) => i.nh('common.problems', n, {command: 'desk'}))",
            "missing": "i.t('no.such.key')",
            "day": "[i.day('2026-09-24'), i.day('later')]",
            "keep": "i.t('qa.minutes')",
        },
        data,
        prelude="const i = I.makeI18n(D.strings, 'uk'); console.warn = () => {};",
    )
    assert r["t"] == "D-1: відповідь <b>"  # t() is for textContent: no escaping
    assert r["h"].startswith("<strong>Запарковано:</strong>") and "<b>&lt;img src=x&gt;</b>" in r["h"]
    assert r["raw"] == "Він з’явиться тут, коли AI створить <code>f</code>."
    assert r["n"] == ["Ще 1 без позначки.", "Ще 3 без позначки.", "Ще 5 без позначки."]
    assert r["plural"][0].startswith("У 1 файлі") and r["plural"][1].startswith("У 3 файлах")
    assert r["plural"][3].startswith("У 21 файлі") and "<code>desk validate</code>" in r["plural"][2]
    assert r["missing"] == "no.such.key"
    assert r["day"] == ["24 вересня", "later"]
    assert r["keep"] == "~{n} хв"  # a placeholder without a value stays visible


def test_link_text_only_links_http() -> None:
    r = node_eval(
        {"U": "js/util.js"},
        {
            "link": "U.linkText('Open http://localhost:3000/week. Then <b>')",
            "js": "U.linkText('javascript:alert(1) and <script>')",
            "amp": "U.linkText('http://x.test/a?b=1&c=2')",
        },
        {},
    )
    assert r["link"] == (
        'Open <a href="http://localhost:3000/week" target="_blank" rel="noopener">'
        "http://localhost:3000/week</a>. Then &lt;b&gt;"
    )
    assert "<a" not in r["js"] and "&lt;script&gt;" in r["js"]
    assert '<a href="http://x.test/a?b=1&amp;c=2"' in r["amp"]


# --------------------------------------------------------------------------- decisions


def decisions_data(tmp_path: Path, repo: Path, lang: str) -> dict[str, Any]:
    parked_root = make_repo(tmp_path / "p", parked(DECISION, "b"))
    p = dec(parked_root)
    return {
        "strings": strings(lang),
        "blocking": dec(repo).list_json()["decisions"][0],
        "blocking_detail": dec(repo).detail_json(dec(repo).find("D-0001")),
        "parked": p.list_json()["decisions"][0],
        "parked_detail": p.detail_json(p.find("D-0001")),
        "no_about": dec(make_repo(tmp_path / "n", DECISION.replace(ABOUT_BLOCK, ""))).list_json()["decisions"][0],
        "xss": {"id": "D-9", "status": "pending", "default": "<b>", "about": "<script>x</script>", "title": "<i>t</i>"},
    }


DECISION_CALLS = {
    "row": "R.rowAboutHtml(D.parked, 'uk')",
    "row_fallback": "R.rowAboutHtml(D.no_about, 'uk')",
    "box": "R.aboutHtml(D.parked_detail, v)",
    "box_none": "R.aboutHtml(D.no_about, v)",
    "badge": "R.parkedBadgeHtml(D.parked, i)",
    "badge_blocking": "R.parkedBadgeHtml(D.blocking, i)",
    "line": "R.parkedLineHtml(D.parked_detail, 'b · Cool', i)",
    "line_blocking": "R.parkedLineHtml(D.blocking, 'x', i)",
    "flags": "[R.isParked(D.parked), R.isBlockingNow(D.parked), R.isParked(D.blocking), R.isBlockingNow(D.blocking)]",
    "xss": "R.aboutHtml(D.xss, v) + R.parkedBadgeHtml(D.xss, i) + R.rowHtml(D.xss, null, v)",
    "detail": "R.detailHtml(D.blocking_detail, {choice: null, comment: ''}, [], v)",
    "picked": "R.detailHtml(D.blocking_detail, {choice: 'b', comment: '<x>'}, [], v)",
    "list": "R.listHtml([D.blocking, D.parked], 'D-0001', v)",
    "empty_inbox": "R.emptyListHtml([{status: 'answered'}, {status: 'answered'}], 'inbox', false, v)",
    "empty_all": "R.emptyListHtml([], 'all', false, v)",
    "keys": "[R.pickKeys(D.blocking_detail, i), R.pickKeys({}, i)]",
}


def test_render_decisions_in_ukrainian(tmp_path: Path, repo: Path) -> None:
    r = node_eval(
        {**I18N, "R": "modules/decisions/render.js"}, DECISION_CALLS, decisions_data(tmp_path, repo, "uk"), view("uk")
    )
    esc_about = ABOUT.replace("&", "&amp;").replace('"', "&quot;")

    assert r["row"] == f'<div class="row-about" lang="uk">{esc_about}</div>'
    assert "Питання: тепла чи холодна палітра?" in r["row_fallback"]  # tldr line 1 when there is no about
    assert "Про що питання" in r["box"] and esc_about in r["box"]
    assert r["box_none"] == ""
    assert "Запарковано · b" in r["badge"] and r["badge_blocking"] == ""
    assert r["line"] == (
        '<p class="parked-line"><strong>Запарковано:</strong> AI працює з варіантом <b>b · Cool</b>, '
        "поки ти не відповіси. Відповідь пізніше може змінити вже зроблене.</p>"
    )
    assert r["line_blocking"] == ""
    assert r["flags"] == [True, False, False, True]
    assert "<script>" not in r["xss"] and "&lt;script&gt;" in r["xss"] and "&lt;b&gt;" in r["xss"]
    assert "<i>t</i>" not in r["xss"] and "&lt;i&gt;t&lt;/i&gt;" in r["xss"]
    d = r["detail"]
    assert "Твоє рішення" in d and "Зберегти відповідь <kbd>⌘↵</kbd>" in d and "1–2 — вибрати" in d
    assert "Високий пріоритет" in d and "Блокує роботу" in d and "AI радить" in d
    assert "&lt;x&gt;</textarea>" in r["picked"] and "<x>" not in r["picked"]
    assert "Чекає" in r["list"] and 'id="row-D-0001"' in r["list"] and 'aria-selected="true"' in r["list"]
    assert "2 рішення з відповіддю чекають на AI." in r["empty_inbox"]
    assert '<span class="mono">decisions/</span>' in r["empty_all"]
    assert r["keys"] == ["1–2", "цифру"]


def test_render_decisions_in_english(tmp_path: Path, repo: Path) -> None:
    r = node_eval(
        {**I18N, "R": "modules/decisions/render.js"}, DECISION_CALLS, decisions_data(tmp_path, repo, "en"), view("en")
    )
    assert "What this is about" in r["box"]
    assert "Parked · b" in r["badge"]
    assert r["line"] == (
        '<p class="parked-line"><strong>Parked:</strong> the AI works with option <b>b · Cool</b> until you '
        "answer. A later answer can change work already done.</p>"
    )
    assert "Your call" in r["detail"] and "Save answer <kbd>⌘↵</kbd>" in r["detail"] and "1–2 to choose" in r["detail"]
    assert "2 answered decisions are waiting on the AI." in r["empty_inbox"]
    assert r["keys"] == ["1–2", "a number"]
    # The content language marks only the content, not the UI labels.
    assert 'lang="uk"' in r["box"] and r["box"].count('lang="') == 1


# --------------------------------------------------------------------------- the plan


def plan_data(root: Path, lang: str) -> dict[str, Any]:
    plan = Desk(root).get("plan").plan_json()  # type: ignore[union-attr]
    xss = json.loads(json.dumps(plan))
    xss["phases"][1]["items"][2]["title"] = "<img src=x onerror=alert(1)>"
    xss["actions"][0]["note"] = "<script>x</script>"
    xss["phases"][1]["items"][0]["links"][0]["path"] = '"><b>'
    return {
        "strings": strings(lang),
        "plan": plan,
        "xss": xss,
        "missing": {"file": "plan/roadmap.yaml", "exists": False},
        "broken": {"file": "plan/roadmap.yaml", "exists": True, "error": "invalid YAML at line 2: <oops>"},
    }


PLAN_CALLS = {
    "html": "R.planHtml(D.plan, {}, v)",
    "p1_open": "R.planHtml(D.plan, {P1: true, P2: false}, v)",
    "no_links": "R.planHtml(D.plan, {}, {...v, links: false})",
    "xss": "R.planHtml(D.xss, {}, v)",
    "missing": "R.planHtml(D.missing, {}, v)",
    "broken": "R.planHtml(D.broken, {}, v)",
    "loading": "R.planHtml(null, {}, v)",
    "human": "[R.waitsOnHuman(D.plan.phases[0].items[1], D.plan), R.waitsOnHuman(D.plan.phases[1].items[1], D.plan)]",
}


def test_render_plan_in_ukrainian(plan_repo: Path) -> None:
    r = node_eval({**I18N, "R": "modules/plan/render.js"}, PLAN_CALLS, plan_data(plan_repo, "uk"), view("uk"))
    html = r["html"]

    assert 'оновлено <time datetime="2026-09-20">20 вересня</time>' in html
    for label in ("Зараз", "Далі", "Від тебе"):
        assert f">{label}<" in html or f">{label} <" in html
    # "Ви тут" marks the now item, once, and only it is the current step.
    assert html.count("Ви тут") == 1 and html.count('aria-current="step"') == 1
    assert 'id="plan-item-S1" aria-current="step"' in html
    # Done phases start collapsed, the one with `now` open; the viewer's clicks win.
    assert 'aria-expanded="false" aria-controls="plan-items-P1"' in html and 'id="plan-items-P1" hidden' in html
    assert 'aria-expanded="true" aria-controls="plan-items-P2"' in html and 'id="plan-items-P2">' in html
    assert 'id="plan-items-P1">' in r["p1_open"] and 'id="plan-items-P2" hidden' in r["p1_open"]
    assert 'data-phase="P3"' not in html  # nothing to expand in an empty phase
    # Status chips, counters, needs, decision chips and links.
    assert "Чекає на тебе" in html and r["human"] == [True, False]
    assert ">1/2<" in html and ">1/4<" in html and "готово 1 з 4" in html
    assert '<span class="needs-label">Потрібно:</span> Твоя відповідь.' in html
    assert 'href="#decisions/D-0001" data-decision="D-0001"' in html and "si-pending is-blocking" in html
    assert 'href="#decisions/' not in r["no_links"] and '<span class="dchip"' in r["no_links"]
    assert 'href="/preview/design/x/preview.png" target="_blank" rel="noopener" data-view="image"' in html
    assert 'data-view="markdown"' in r["p1_open"]
    # The trail: solid where both ends are reached, dotted ahead, no line after the last node.
    assert "is-here seg-dotted" in html and html.count("seg-end") == 1
    # Everything from YAML is escaped.
    x = r["xss"]
    assert "<img src=x" not in x and "&lt;img src=x onerror=alert(1)&gt;" in x
    assert "<script>" not in x and '"><b>' not in x
    # Empty, broken and loading states.
    assert "Плану ще немає" in r["missing"] and "<code>plan/roadmap.yaml</code>" in r["missing"]
    assert "Не вдалося прочитати план" in r["broken"] and "&lt;oops&gt;" in r["broken"]
    assert "<code>desk validate</code>" in r["broken"]
    assert r["loading"] == ""


def test_render_plan_in_english(plan_repo: Path) -> None:
    r = node_eval({**I18N, "R": "modules/plan/render.js"}, PLAN_CALLS, plan_data(plan_repo, "en"), view("en"))
    html = r["html"]
    assert 'updated <time datetime="2026-09-20">20 September</time>' in html
    assert html.count("You are here") == 1 and "Waiting on you" in html and "1 of 4 done" in html
    assert '<span class="needs-label">Needs:</span>' in html
    assert "No plan yet" in r["missing"] and "Could not read the plan" in r["broken"]


# --------------------------------------------------------------------------- QA runs


def qa_data(root: Path, lang: str) -> dict[str, Any]:
    k = qa(root)
    k.mark_case("R-0001", "T01", {"result": "fail", "note": "<b>зламано</b>"})
    run = k.detail_json(k.find("R-0001"))
    full = json.loads(json.dumps(run))
    for c in full["cases"]:
        c["result"] = "pass"
    full["marked"] = 3
    xss = json.loads(json.dumps(run))
    xss["title"] = "<img src=x onerror=alert(1)>"
    xss["cases"][0]["steps"] = ["<script>x</script> http://localhost:3000/a?b=1&c=2."]
    xss["cases"][0]["where"] = "javascript:alert(1)"
    processed = json.loads(json.dumps(full)) | {"status": "processed"}
    processed["cases"][0]["ai"] = "fixed in abc123"
    return {"strings": strings(lang), "qa": k.qa_json(), "run": run, "full": full, "xss": xss, "processed": processed}


QA_CALLS = {
    "list": "R.qaListHtml(D.qa, 'R-0001', v)",
    "empty": "R.qaListHtml({runs: [], dir: 'qa/runs'}, null, v)",
    "run": "R.qaRunHtml(D.run, {current: 'T01', notes: {}}, v)",
    "t2": "R.qaRunHtml(D.run, {current: 'T02', notes: {T02: 'чернетка'}, overall: 'враження'}, v)",
    "full": "R.qaRunHtml(D.full, {current: 'T01'}, v)",
    "xss": "R.qaRunHtml(D.xss, {current: 'T01'}, v)",
    "processed": "R.qaRunHtml(D.processed, {current: 'T01'}, v)",
    "next": (
        "[R.nextUnmarked(D.run, 'T01'), R.nextUnmarked(D.run, 'T03'), R.nextUnmarked(D.full, 'T01'),"
        " R.firstCase(D.run), R.firstCase(D.full)]"
    ),
    "waiting": "R.waitingRuns(D.qa).map((r) => r.id)",
}


def test_render_qa_in_ukrainian(qa_repo: Path) -> None:
    r = node_eval({**I18N, "R": "modules/qa/render.js"}, QA_CALLS, qa_data(qa_repo, "uk"), view("uk"))

    assert 'data-run="R-0001"' in r["list"] and "1/3 позначено" in r["list"] and "не пройшло: 1" in r["list"]
    assert ">Чекають на тебе<" in r["list"] and "~25 хв" in r["list"]
    assert "Ранів ще немає" in r["empty"] and "qa/runs/" in r["empty"]
    html = r["run"]
    # The open case: why, where (new tab), steps, expected, the four marks with keys, the note.
    assert 'href="http://localhost:3000/" target="_blank" rel="noopener"' in html
    assert "<li>Натисни «Get started».</li>" in html and "<li>Одразу відкривається результат.</li>" in html
    for label, key in (("Пройшло", "p"), ("Не пройшло", "f"), ("Заблоковано", "b"), ("Пропустити", "s")):
        assert f"{label} <kbd>{key}</kbd>" in html
    assert 'data-mark="fail" data-case="T01" aria-pressed="true"' in html
    assert "&lt;b&gt;зламано&lt;/b&gt;" in html and "<b>зламано" not in html
    assert html.count('class="qa-case-body"') == 1 and 'aria-expanded="false" aria-controls="qa-body-T02"' in html
    assert 'data-action="finish" disabled' in html and "Ще 2 без позначки." in html
    assert html.count("qa-seg res-none") == 2 and "qa-seg res-fail is-current" in html
    # Drafts win over saved text.
    assert ">чернетка</textarea>" in r["t2"] and ">враження</textarea>" in r["t2"]
    assert 'data-action="finish">' in r["full"] and "Ще " not in r["full"]
    # Processed: read-only, with the AI's line; no finish button.
    p = r["processed"]
    assert "Оброблено" in p and "fixed in abc123" in p and 'data-action="finish"' not in p
    assert 'aria-pressed="true" disabled' in p and "readonly" in p
    # Everything is escaped; only http(s) becomes a link.
    x = r["xss"]
    assert "<img src=x" not in x and "<script>" not in x and 'href="javascript' not in x
    assert '<a href="http://localhost:3000/a?b=1&amp;c=2" target="_blank" rel="noopener">' in x
    assert r["next"] == ["T02", "T02", None, "T02", "T01"]
    assert r["waiting"] == ["R-0001"]


def test_render_qa_in_english(qa_repo: Path) -> None:
    r = node_eval({**I18N, "R": "modules/qa/render.js"}, QA_CALLS, qa_data(qa_repo, "en"), view("en"))
    assert "1/3 marked" in r["list"] and "failed: 1" in r["list"] and "~25 min" in r["list"]
    for label, key in (("Pass", "p"), ("Fail", "f"), ("Blocked", "b"), ("Skip", "s")):
        assert f"{label} <kbd>{key}</kbd>" in r["run"]
    assert "2 still unmarked." in r["run"] and "Finish the run" in r["run"]
    assert "No runs yet." in r["empty"] and "Processed" in r["processed"]
