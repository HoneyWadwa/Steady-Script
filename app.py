from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3, random
from datetime import datetime
from pathlib import Path

BASE=Path(__file__).resolve().parent
DB=BASE/"data"/"steady_script.db"
app=Flask(__name__)

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def init_db():
    DB.parent.mkdir(exist_ok=True)
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS sessions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
      ended_at TEXT, duration_s REAL DEFAULT 0, quality_score REAL DEFAULT 0,
      freeze_events INTEGER DEFAULT 0, cue_events INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS strokes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
      timestamp TEXT NOT NULL, duration_ms INTEGER DEFAULT 0,
      amplitude_index REAL DEFAULT 0, speed_index REAL DEFAULT 0,
      pressure REAL DEFAULT 0, distance_mm REAL DEFAULT 0,
      FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL,
      timestamp TEXT NOT NULL, event_type TEXT NOT NULL, value REAL DEFAULT 0,
      FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS calibration(
      id INTEGER PRIMARY KEY CHECK(id=1), baseline_amplitude REAL DEFAULT 1,
      baseline_speed REAL DEFAULT 1, small_stroke_threshold REAL DEFAULT .65,
      freeze_threshold REAL DEFAULT .20, freeze_duration_ms INTEGER DEFAULT 500);
    INSERT OR IGNORE INTO calibration VALUES(1,1,1,.65,.20,500);
    """)
    c.commit(); c.close()

def score(a,s,f):
    return round(.4*min(100,max(0,a*100))+.3*min(100,max(0,s*100))+.3*max(0,100-f*10),1)

@app.route("/")
def home():
    c=db()
    latest=c.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    strokes=[dict(x) for x in c.execute("SELECT * FROM strokes ORDER BY id DESC LIMIT 12").fetchall()]
    events=[dict(x) for x in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 10").fetchall()]
    cal=dict(c.execute("SELECT * FROM calibration WHERE id=1").fetchone()); c.close()
    return render_template("dashboard.html",latest=dict(latest) if latest else None,strokes=strokes,events=events,calibration=cal)

@app.route("/sessions")
def sessions():
    c=db(); rows=[dict(x) for x in c.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()]; c.close()
    return render_template("sessions.html",sessions=rows)

@app.route("/session/<int:sid>")
def detail(sid):
    c=db(); s=c.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
    if not s: c.close(); return "Session not found",404
    strokes=[dict(x) for x in c.execute("SELECT * FROM strokes WHERE session_id=? ORDER BY id",(sid,)).fetchall()]
    events=[dict(x) for x in c.execute("SELECT * FROM events WHERE session_id=? ORDER BY id",(sid,)).fetchall()]
    c.close(); return render_template("detail.html",session=dict(s),strokes=strokes,events=events)

@app.route("/calibration",methods=["GET","POST"])
def calibration():
    c=db()
    if request.method=="POST":
        c.execute("""UPDATE calibration SET baseline_amplitude=?,baseline_speed=?,
        small_stroke_threshold=?,freeze_threshold=?,freeze_duration_ms=? WHERE id=1""",
        (float(request.form["baseline_amplitude"]),float(request.form["baseline_speed"]),
         float(request.form["small_stroke_threshold"]),float(request.form["freeze_threshold"]),
         int(request.form["freeze_duration_ms"])))
        c.commit()
    cal=dict(c.execute("SELECT * FROM calibration WHERE id=1").fetchone()); c.close()
    return render_template("calibration.html",calibration=cal)

@app.post("/api/ingest")
def ingest():
    d=request.get_json(silent=True) or {}
    if not all(k in d for k in ("session_id","stroke_amp","speed")):
        return jsonify(error="session_id, stroke_amp and speed are required"),400
    sid=int(d["session_id"]); now=datetime.now().isoformat(timespec="seconds")
    amp=float(d["stroke_amp"]); sp=float(d["speed"]); pressure=float(d.get("pressure",0))
    dist=float(d.get("distance_mm",0)); freeze=int(d.get("freeze",0)); cue=int(d.get("cue",0))
    c=db(); c.execute("INSERT OR IGNORE INTO sessions(id,started_at) VALUES(?,?)",(sid,now))
    c.execute("""INSERT INTO strokes(session_id,timestamp,duration_ms,amplitude_index,
      speed_index,pressure,distance_mm) VALUES(?,?,?,?,?,?,?)""",
      (sid,now,int(d.get("stroke_duration_ms",0)),amp,sp,pressure,dist))
    if amp < .65: c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,?)",(sid,now,"SMALL_STROKE",amp))
    if freeze: c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,1)",(sid,now,"FREEZE_LIKE_EVENT"))
    if cue: c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,1)",(sid,now,"HAPTIC_CUE"))
    r=c.execute("SELECT AVG(amplitude_index) a,AVG(speed_index) s FROM strokes WHERE session_id=?",(sid,)).fetchone()
    f=c.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND event_type='FREEZE_LIKE_EVENT'",(sid,)).fetchone()[0]
    q=score(r["a"] or 0,r["s"] or 0,f)
    cues=c.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND event_type='HAPTIC_CUE'",(sid,)).fetchone()[0]
    c.execute("UPDATE sessions SET quality_score=?,freeze_events=?,cue_events=? WHERE id=?",(q,f,cues,sid))
    c.commit(); c.close(); return jsonify(ok=True,session_id=sid,quality_score=q)

@app.post("/api/simulate")
def simulate():
    c=db(); sid=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM sessions").fetchone()[0]
    now=datetime.now().isoformat(timespec="seconds"); c.execute("INSERT INTO sessions(id,started_at) VALUES(?,?)",(sid,now))
    amps=[.92,.88,.81,.76,.58,.54,.82,.91,.63,.48,.85,.89]
    speeds=[.90,.88,.84,.80,.70,.65,.78,.86,.72,.60,.82,.88]
    for a,s in zip(amps,speeds):
        ts=datetime.now().isoformat(timespec="seconds")
        c.execute("""INSERT INTO strokes(session_id,timestamp,duration_ms,amplitude_index,
        speed_index,pressure,distance_mm) VALUES(?,?,?,?,?,?,?)""",
        (sid,ts,random.randint(250,650),a,s,round(random.uniform(.35,.75),2),round(random.uniform(1.5,4),2)))
        if a<.65:
            c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,?)",(sid,ts,"SMALL_STROKE",a))
            c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,1)",(sid,ts,"HAPTIC_CUE"))
    c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,1)",(sid,now,"FREEZE_LIKE_EVENT"))
    c.execute("INSERT INTO events(session_id,timestamp,event_type,value) VALUES(?,?,?,1)",(sid,now,"HAPTIC_CUE"))
    q=score(sum(amps)/len(amps),sum(speeds)/len(speeds),1)
    cues=c.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND event_type='HAPTIC_CUE'",(sid,)).fetchone()[0]
    c.execute("UPDATE sessions SET ended_at=?,duration_s=?,quality_score=?,freeze_events=1,cue_events=? WHERE id=?",(now,45,q,cues,sid))
    c.commit(); c.close(); return redirect(url_for("detail",sid=sid))

@app.post("/api/reset")
def reset():
    c=db(); c.execute("DELETE FROM events"); c.execute("DELETE FROM strokes"); c.execute("DELETE FROM sessions"); c.commit(); c.close()
    return redirect(url_for("home"))

if __name__=="__main__":
    init_db(); app.run(host="127.0.0.1",port=5001,debug=True)
