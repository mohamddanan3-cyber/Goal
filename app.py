import os, sqlite3, math, json
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
import requests
from functools import lru_cache
from datetime import date, timedelta

app = Flask(__name__)
DB_PATH = os.environ.get("DATABASE_PATH", "goalgpt.db")
FOOTBALL_API_KEY = os.environ.get("APISPORTS_KEY", "").strip()
FOOTBALL_API_BASE = "https://v3.football.api-sports.io"
FOOTBALL_TIMEZONE = os.environ.get("FOOTBALL_TIMEZONE", "Africa/Casablanca")

BOTS = [
    {"id":"cipher","name":"Cipher-X","style":"تحليل إحصائي متقدم","attack":0.52,"defense":0.48,"home":1.04},
    {"id":"stat","name":"StatEngine","style":"قوة الهجوم والدفاع","attack":0.68,"defense":0.32,"home":1.03},
    {"id":"code","name":"CodeHome","style":"أفضلية الأرض والأداء العام","attack":0.48,"defense":0.52,"home":1.12},
    {"id":"deep","name":"DeepScore","style":"توزيع بواسون والنتيجة الدقيقة","attack":0.55,"defense":0.45,"home":1.00},
    {"id":"engine","name":"Engine-X","style":"مؤشرات هجومية ودفاعية","attack":0.62,"defense":0.38,"home":1.06},
    {"id":"alert","name":"Alert System","style":"إشارات الأهداف","attack":0.58,"defense":0.42,"home":1.02},
    {"id":"strike","name":"StrikeBot","style":"تقدير إيقاع المباراة","attack":0.50,"defense":0.50,"home":1.08},
    {"id":"metric","name":"MetricBot","style":"دمج المؤشرات","attack":0.60,"defense":0.40,"home":1.05},
]

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            home TEXT NOT NULL, away TEXT NOT NULL,
            bot_id TEXT NOT NULL, bot_name TEXT NOT NULL,
            home_xg REAL NOT NULL, away_xg REAL NOT NULL,
            pick TEXT NOT NULL, score TEXT NOT NULL,
            over25 REAL NOT NULL, btts REAL NOT NULL,
            actual_home INTEGER, actual_away INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING'
        )""")

def poisson(lam, k):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def analyze(home_scored, home_conceded, away_scored, away_conceded, bot):
    # All inputs are per-match averages. Clamp to prevent extreme or invalid values.
    hs, hc, aws, awc = [max(0.05, min(5.0, float(x))) for x in
                        (home_scored, home_conceded, away_scored, away_conceded)]
    league_home, league_away = 1.45, 1.15
    h_attack = hs / league_home
    a_def = awc / league_home
    a_attack = aws / league_away
    h_def = hc / league_away
    home_xg = league_home * (h_attack ** bot["attack"]) * (a_def ** bot["defense"]) * bot["home"]
    away_xg = league_away * (a_attack ** bot["attack"]) * (h_def ** bot["defense"])
    home_xg = max(0.15, min(4.2, home_xg))
    away_xg = max(0.15, min(4.2, away_xg))

    grid = [[poisson(home_xg, i) * poisson(away_xg, j) for j in range(9)] for i in range(9)]
    p_home = sum(grid[i][j] for i in range(9) for j in range(9) if i > j)
    p_draw = sum(grid[i][j] for i in range(9) for j in range(9) if i == j)
    p_away = sum(grid[i][j] for i in range(9) for j in range(9) if i < j)
    total = p_home + p_draw + p_away
    p_home, p_draw, p_away = [p / total for p in (p_home, p_draw, p_away)]
    pick = max([("1", p_home), ("X", p_draw), ("2", p_away)], key=lambda x:x[1])[0]
    scores = sorted(((grid[i][j], f"{i}-{j}") for i in range(9) for j in range(9)), reverse=True)
    over25 = 1 - sum(grid[i][j] for i in range(9) for j in range(9) if i+j <= 2)
    btts = sum(grid[i][j] for i in range(1,9) for j in range(1,9))
    return {
        "home_xg": round(home_xg, 2), "away_xg": round(away_xg, 2),
        "p_home": round(p_home*100, 1), "p_draw": round(p_draw*100, 1),
        "p_away": round(p_away*100, 1), "pick": pick,
        "score": scores[0][1], "top_scores": [s for _,s in scores[:3]],
        "over25": round(over25*100, 1), "btts": round(btts*100, 1)
    }



def football_api(endpoint, params=None):
    """Server-side API-Football request. The API key is never exposed to the browser."""
    if not FOOTBALL_API_KEY:
        raise RuntimeError("خاصك تزيد APISPORTS_KEY فإعدادات Environment Variables.")
    try:
        response = requests.get(
            f"{FOOTBALL_API_BASE}/{endpoint.lstrip('/')}",
            headers={"x-apisports-key": FOOTBALL_API_KEY},
            params=params or {},
            timeout=18
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        raise RuntimeError("تعذر الاتصال بمصدر بيانات المباريات. حاول من جديد بعد قليل.")
    if payload.get("errors"):
        raise RuntimeError("مصدر البيانات رفض الطلب: " + str(payload["errors"])[:240])
    return payload.get("response", [])

def number_or_none(value):
    try:
        if value in (None, "", "-"):
            return None
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None

def team_goal_averages(stats, venue):
    goals = stats.get("goals") or {}
    scored = number_or_none((((goals.get("for") or {}).get("average") or {}).get(venue)))
    conceded = number_or_none((((goals.get("against") or {}).get("average") or {}).get(venue)))
    return scored, conceded

@app.get("/api/provider-status")
def provider_status():
    return jsonify({"configured": bool(FOOTBALL_API_KEY),
                    "provider": "API-Football",
                    "message": "مصدر البيانات مربوط." if FOOTBALL_API_KEY else
                    "خاصك API Key باش يتفعّل جلب المباريات تلقائياً."})

@app.get("/api/fixtures")
def fixtures():
    if not FOOTBALL_API_KEY:
        return jsonify(error="خاصك تضيف APISPORTS_KEY باش تجيب المباريات مباشرة.",
                       needs_key=True), 503
    requested_date = request.args.get("date", date.today().isoformat())
    try:
        date.fromisoformat(requested_date)
    except ValueError:
        return jsonify(error="التاريخ غير صحيح."), 400
    try:
        rows = football_api("fixtures", {"date": requested_date, "timezone": FOOTBALL_TIMEZONE})
        matches = []
        for item in rows:
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            home_team, away_team = teams.get("home") or {}, teams.get("away") or {}
            goals = item.get("goals") or {}
            matches.append({
                "id": fixture.get("id"),
                "date": fixture.get("date"),
                "timestamp": fixture.get("timestamp"),
                "status": (fixture.get("status") or {}).get("short"),
                "status_long": (fixture.get("status") or {}).get("long"),
                "elapsed": (fixture.get("status") or {}).get("elapsed"),
                "venue": (fixture.get("venue") or {}).get("name"),
                "league": league.get("name"),
                "country": league.get("country"),
                "league_logo": league.get("logo"),
                "home": home_team.get("name"),
                "home_logo": home_team.get("logo"),
                "home_id": home_team.get("id"),
                "away": away_team.get("name"),
                "away_logo": away_team.get("logo"),
                "away_id": away_team.get("id"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away")
            })
        return jsonify(matches)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502

@app.post("/api/fixture/<int:fixture_id>/analyze")
def analyze_fixture(fixture_id):
    if not FOOTBALL_API_KEY:
        return jsonify(error="خاصك تضيف APISPORTS_KEY باش تحلل مباراة تلقائياً.",
                       needs_key=True), 503
    try:
        fixture_rows = football_api("fixtures", {"id": fixture_id, "timezone": FOOTBALL_TIMEZONE})
        if not fixture_rows:
            return jsonify(error="المباراة غير موجودة عند مزود البيانات."), 404
        item = fixture_rows[0]
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        home_team, away_team = teams.get("home") or {}, teams.get("away") or {}
        league_id, season = league.get("id"), league.get("season")
        home_id, away_id = home_team.get("id"), away_team.get("id")
        if not all((league_id, season, home_id, away_id)):
            return jsonify(error="المعطيات الأساسية ديال المباراة ناقصة."), 422

        home_stats_rows = football_api("teams/statistics", {
            "league": league_id, "season": season, "team": home_id
        })
        away_stats_rows = football_api("teams/statistics", {
            "league": league_id, "season": season, "team": away_id
        })
        if not home_stats_rows or not away_stats_rows:
            return jsonify(error="إحصائيات هاد الدوري أو الفريقين غير متوفرة حالياً."), 422

        # Prefer venue-specific averages; fall back to overall averages when needed.
        h_scored, h_conceded = team_goal_averages(home_stats_rows[0], "home")
        a_scored, a_conceded = team_goal_averages(away_stats_rows[0], "away")
        if h_scored is None or h_conceded is None:
            h_scored, h_conceded = team_goal_averages(home_stats_rows[0], "total")
        if a_scored is None or a_conceded is None:
            a_scored, a_conceded = team_goal_averages(away_stats_rows[0], "total")
        if None in (h_scored, h_conceded, a_scored, a_conceded):
            return jsonify(error="مزود البيانات ما رجعش متوسطات أهداف كافية لتحليل هاد المباراة."), 422

        values = [h_scored, h_conceded, a_scored, a_conceded]
        output = []
        now = datetime.now(timezone.utc).isoformat()
        home_name, away_name = home_team.get("name", "Home"), away_team.get("name", "Away")
        with db() as con:
            for bot in BOTS:
                result = analyze(*values, bot)
                con.execute("""INSERT INTO predictions
                    (created_at,home,away,bot_id,bot_name,home_xg,away_xg,pick,score,over25,btts)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (now,home_name,away_name,bot["id"],bot["name"],result["home_xg"],result["away_xg"],
                     result["pick"],result["score"],result["over25"],result["btts"]))
                output.append({"id":con.execute("SELECT last_insert_rowid()").fetchone()[0],
                               "name":bot["name"],"style":bot["style"],**result})
        return jsonify({
            "home": home_name, "away": away_name, "bots": output,
            "source": "API-Football",
            "averages": {"home_scored": h_scored, "home_conceded": h_conceded,
                         "away_scored": a_scored, "away_conceded": a_conceded}
        })
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502

@app.route("/")
def home():
    return render_template("index.html", bots=BOTS)

@app.get("/api/bots")
def bots():
    with db() as con:
        result = []
        for bot in BOTS:
            rows = con.execute("SELECT status FROM predictions WHERE bot_id=?", (bot["id"],)).fetchall()
            won = sum(1 for r in rows if r["status"] == "WON")
            lost = sum(1 for r in rows if r["status"] == "LOST")
            settled = won + lost
            result.append({"id":bot["id"], "name":bot["name"], "style":bot["style"],
                           "predictions":len(rows), "won":won, "lost":lost,
                           "accuracy": round(won/settled*100,1) if settled else None})
    return jsonify(result)

@app.post("/api/predict")
def predict():
    data = request.get_json(silent=True) or {}
    try:
        home = str(data.get("home","")).strip()[:60]
        away = str(data.get("away","")).strip()[:60]
        if not home or not away or home.casefold() == away.casefold():
            return jsonify(error="أدخل اسمَي فريقين مختلفين."), 400
        values = [float(data[k]) for k in ("home_scored","home_conceded","away_scored","away_conceded")]
        if any(not math.isfinite(v) or v < 0 or v > 10 for v in values):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        return jsonify(error="أدخل متوسطات صحيحة بين 0 و10 أهداف."), 400

    output = []
    now = datetime.now(timezone.utc).isoformat()
    with db() as con:
        for bot in BOTS:
            result = analyze(*values, bot)
            con.execute("""INSERT INTO predictions
                (created_at,home,away,bot_id,bot_name,home_xg,away_xg,pick,score,over25,btts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (now,home,away,bot["id"],bot["name"],result["home_xg"],result["away_xg"],
                 result["pick"],result["score"],result["over25"],result["btts"]))
            output.append({"id":con.execute("SELECT last_insert_rowid()").fetchone()[0],
                           "name":bot["name"],"style":bot["style"],**result})
    return jsonify({"home":home,"away":away,"bots":output,"source":"manual"})

@app.get("/api/history")
def history():
    with db() as con:
        rows = con.execute("""SELECT id,created_at,home,away,bot_name,pick,score,status
                              FROM predictions ORDER BY id DESC LIMIT 60""").fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/result/<int:prediction_id>")
def set_result(prediction_id):
    data = request.get_json(silent=True) or {}
    try:
        ah, aa = int(data["home"]), int(data["away"])
        if not (0 <= ah <= 30 and 0 <= aa <= 30): raise ValueError()
    except (KeyError, TypeError, ValueError):
        return jsonify(error="النتيجة غير صحيحة."), 400
    with db() as con:
        row = con.execute("SELECT pick,score FROM predictions WHERE id=?", (prediction_id,)).fetchone()
        if not row: return jsonify(error="التوقع غير موجود."), 404
        actual_pick = "1" if ah > aa else ("2" if ah < aa else "X")
        exact = row["score"] == f"{ah}-{aa}"
        # Accuracy leaderboard grades the main 1X2 pick; exact score is retained separately in history.
        status = "WON" if row["pick"] == actual_pick else "LOST"
        con.execute("UPDATE predictions SET actual_home=?,actual_away=?,status=? WHERE id=?",
                    (ah,aa,status,prediction_id))
    return jsonify(ok=True,status=status,exact_score=exact)

@app.get("/health")
def health():
    return {"ok": True, "app": "GOALGPT"}

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
