#!/usr/bin/env python3
"""Trivia night score keeper, shared through GitHub.

Everything lives in this git repo: scores.json holds the scores and index.html
is the public scoreboard served by GitHub Pages from main. Every change pulls
the latest scores from GitHub, applies the change, regenerates index.html,
commits and pushes to main. If another co-host pushed in the meantime, it
pulls again and re-applies the change automatically.

Commands
  show                               print the leaderboard (pulls latest first)
  teams "Name One" "Name Two" ...    add teams (numbered T1, T2, ... + initials)
  round N T1=8 T2=6.5 QB=7           set round N scores (by T#, number, initials or name)
  round N 8 6 7 5 9                  set round N scores for every team, in team order
  adjust T3 -2 "reason"              bonus/penalty outside a round
  rename T2 "New Name"               rename a team
  delround N                         remove a round entirely
  title "Quiz Night"                 set the scoreboard title
  undo                               revert the most recent change (whoever made it)
"""
import datetime
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
STATE = HERE / "scores.json"
TZ = ZoneInfo("America/New_York")
STOP = {"the", "a", "an", "of", "and", "&", "in", "on", "for", "to"}
EMPTY = {"title": "Trivia Night", "teams": [], "rounds": {}, "adjustments": []}


def git(*args):
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True)


def sync():
    """Get onto main and fast-forward to the latest scores on GitHub."""
    if git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "main":
        r = git("checkout", "-q", "main")
        if r.returncode:
            raise SystemExit(f"Could not switch to main: {r.stderr.strip()}")
    r = git("pull", "-q", "--ff-only", "origin", "main")
    if r.returncode:
        raise SystemExit(f"Could not pull latest scores from GitHub: {r.stderr.strip()}")


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else json.loads(json.dumps(EMPTY))


def commit_and_push(summary):
    git("add", "scores.json", "index.html")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return "nochange"
    trailers = git("config", "--get", "score.trailers").stdout.strip()
    msg = f"Scores: {summary}" + (f"\n\n{trailers}" if trailers else "")
    r = git("commit", "-q", "-m", msg)
    if r.returncode:
        raise SystemExit(f"Commit failed: {r.stderr.strip()}")
    if git("push", "-q", "origin", "HEAD:main").returncode == 0:
        return "pushed"
    git("reset", "-q", "--hard", "HEAD~1")  # drop only our own unpushed commit
    return "retry"


def fmt(x):
    if x is None:
        return "–"
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def initials(name, taken):
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name)]
    core = [w for w in words if w.lower() not in STOP] or words
    if len(core) == 1:
        base = core[0][:3].upper()
    else:
        base = "".join(w[0] for w in core[:4]).upper()
    base = base or "TM"
    abbr, n = base, 2
    while abbr in taken:
        abbr, n = f"{base}{n}", n + 1
    return abbr


def resolve(s, token):
    t = token.strip().lower()
    teams = s["teams"]
    for team in teams:
        if t == team["id"].lower() or t == team["id"][1:] or t == team["abbr"].lower():
            return team
    exact = [x for x in teams if x["name"].lower() == t]
    if exact:
        return exact[0]
    partial = [x for x in teams if t in x["name"].lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise SystemExit(f"'{token}' is ambiguous: " + ", ".join(x["name"] for x in partial))
    raise SystemExit(f"No team matches '{token}'. Teams: " + ", ".join(f"{x['id']}={x['name']}" for x in teams))


def num(v):
    try:
        return float(v)
    except ValueError:
        raise SystemExit(f"'{v}' is not a number")


def totals(s):
    rows = []
    rnds = sorted(s["rounds"], key=lambda r: float(r) if re.fullmatch(r"[\d.]+", r) else 1e9)
    for team in s["teams"]:
        per = [s["rounds"][r].get(team["id"]) for r in rnds]
        adj = sum(a["points"] for a in s["adjustments"] if a["team"] == team["id"])
        total = sum(p for p in per if p is not None) + adj
        rows.append({"team": team, "per": per, "adj": adj, "total": total})
    rows.sort(key=lambda r: (-r["total"], int(r["team"]["id"][1:])))
    rank = 0
    for i, row in enumerate(rows):
        if i == 0 or row["total"] != rows[i - 1]["total"]:
            rank = i + 1
        row["rank"] = rank
    return rnds, rows


def table(s):
    rnds, rows = totals(s)
    has_adj = any(r["adj"] for r in rows)
    head = ["#", "Team"] + [f"R{r}" for r in rnds] + (["Adj"] if has_adj else []) + ["**Total**"]
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        t = r["team"]
        cells = [str(r["rank"]), f"{t['id']} · {t['name']} ({t['abbr']})"]
        cells += [fmt(p) for p in r["per"]]
        if has_adj:
            cells.append(f"{r['adj']:+g}" if r["adj"] else "–")
        cells.append(f"**{fmt(r['total'])}**")
        out.append("| " + " | ".join(cells) + " |")
    if s["adjustments"]:
        out.append("")
        out.append("Adjustments: " + "; ".join(
            f"{a['team']} {a['points']:+g}" + (f" ({a['reason']})" if a.get("reason") else "")
            for a in s["adjustments"]))
    return "\n".join(out)


def render(s):
    rnds, rows = totals(s)
    has_adj = any(r["adj"] for r in rows)
    th = "".join(f"<th>R{html.escape(r)}</th>" for r in rnds) + ("<th>Adj</th>" if has_adj else "")
    body = []
    for r in rows:
        t = r["team"]
        cls = ' class="lead"' if r["rank"] == 1 and r["total"] > 0 else ""
        cells = "".join(f"<td>{fmt(p)}</td>" for p in r["per"])
        if has_adj:
            cells += f"<td>{r['adj']:+g}</td>" if r["adj"] else "<td>–</td>"
        body.append(
            f"<tr{cls}><td class=rank>{r['rank']}</td>"
            f"<td class=team><span class=id>{t['id']}</span>{html.escape(t['name'])}</td>"
            f"{cells}<td class=total>{fmt(r['total'])}</td></tr>")
    stamp = datetime.datetime.now(TZ).strftime("%-I:%M %p")
    page = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(s['title'])}</title>
<style>
  body {{ margin:0; font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0; }}
  main {{ max-width:1100px; margin:0 auto; padding:32px 20px; }}
  h1 {{ margin:0 0 4px; font-size:clamp(28px,5vw,48px); }}
  .sub {{ color:#94a3b8; margin-bottom:24px; }}
  table {{ width:100%; border-collapse:collapse; font-size:clamp(16px,2.4vw,26px); }}
  th {{ text-align:center; color:#94a3b8; font-weight:600; padding:10px 8px; border-bottom:2px solid #334155; }}
  th:nth-child(2) {{ text-align:left; }}
  td {{ text-align:center; padding:12px 8px; border-bottom:1px solid #1e293b; font-variant-numeric:tabular-nums; }}
  td.team {{ text-align:left; font-weight:600; }}
  .id {{ display:inline-block; min-width:2.4em; color:#94a3b8; font-weight:500; }}
  td.rank {{ color:#94a3b8; width:2em; }}
  td.total {{ font-weight:800; font-size:1.2em; }}
  tr.lead td {{ background:#1e293b; }}
  tr.lead td.total {{ color:#fbbf24; }}
</style></head>
<body><main>
<h1>{html.escape(s['title'])}</h1>
<div class=sub>{len(rnds)} round{'s' if len(rnds) != 1 else ''} scored · updated {stamp}</div>
<table><thead><tr><th>#</th><th>Team</th>{th}<th>Total</th></tr></thead>
<tbody>{''.join(body) or '<tr><td colspan=3 style="padding:40px;color:#94a3b8">Waiting for teams…</td></tr>'}</tbody></table>
</main>
<script>
// Pull a fresh copy every 10s (bypassing caches) and swap in the new scores.
setInterval(async () => {{
  try {{
    const r = await fetch(location.pathname + "?t=" + Date.now(), {{cache: "no-store"}});
    if (!r.ok) return;
    const doc = new DOMParser().parseFromString(await r.text(), "text/html");
    const fresh = doc.querySelector("main");
    if (fresh && fresh.innerHTML !== document.querySelector("main").innerHTML)
      document.querySelector("main").innerHTML = fresh.innerHTML;
  }} catch (e) {{}}
}}, 10000);
</script>
</body></html>
"""
    (HERE / "index.html").write_text(page)


def apply(s, cmd, args):
    if cmd == "teams":
        taken = {t["abbr"] for t in s["teams"]}
        for name in args:
            if any(t["name"].lower() == name.lower() for t in s["teams"]):
                continue
            abbr = initials(name, taken)
            taken.add(abbr)
            s["teams"].append({"id": f"T{len(s['teams']) + 1}", "name": name, "abbr": abbr})
    elif cmd == "round":
        rnd, entries = args[0], args[1:]
        scores = s["rounds"].setdefault(rnd, {})
        if entries and all(re.fullmatch(r"-?[\d.]+", e) for e in entries):
            if len(entries) != len(s["teams"]):
                raise SystemExit(f"Got {len(entries)} scores for {len(s['teams'])} teams; use T#=score instead.")
            for team, v in zip(s["teams"], entries):
                scores[team["id"]] = num(v)
        else:
            for e in entries:
                key, _, v = e.rpartition("=") if "=" in e else e.rpartition(":")
                scores[resolve(s, key)["id"]] = num(v)
    elif cmd == "adjust":
        team = resolve(s, args[0])
        s["adjustments"].append({"team": team["id"], "points": num(args[1]), "reason": " ".join(args[2:])})
    elif cmd == "rename":
        team = resolve(s, args[0])
        team["name"] = args[1]
        team["abbr"] = initials(args[1], {t["abbr"] for t in s["teams"] if t is not team})
    elif cmd == "delround":
        s["rounds"].pop(args[0], None)
    elif cmd == "title":
        s["title"] = " ".join(args)
    elif cmd == "undo":
        r = git("show", "HEAD~1:scores.json")
        if r.returncode:
            raise SystemExit("Nothing to undo.")
        s.clear()
        s.update(json.loads(r.stdout))
    else:
        raise SystemExit(f"Unknown command '{cmd}'.\n{__doc__}")


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0].lower(), argv[1:]
    if cmd == "show":
        sync()
    else:
        for attempt in range(4):
            sync()
            s = load()
            apply(s, cmd, args)
            STATE.write_text(json.dumps(s, indent=2) + "\n")
            render(s)
            result = commit_and_push(" ".join([cmd, *args]))
            if result != "retry":
                break
            print("Someone else just updated the scores; re-applying on top of theirs...")
        else:
            raise SystemExit("PUSH FAILED after several tries. Scores were NOT published.")
        print("No change." if result == "nochange" else "Published. The live page updates in about a minute.")
    s = load()
    print(f"\n{s['title']}\n")
    print(table(s) if s["teams"] else "(no teams yet)")


if __name__ == "__main__":
    main(sys.argv[1:])
