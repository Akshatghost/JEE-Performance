from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from statistics import mean, median, pstdev
from pathlib import Path
import json, csv, io, math, uuid, sqlite3

BASE = Path(__file__).parent
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE / 'jee_tracker.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Test(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    test_date = db.Column(db.Date, nullable=False)
    test_type = db.Column(db.String(50), default="Custom")
    max_marks = db.Column(db.Float, default=300)
    duration = db.Column(db.Integer, default=180)
    attempt = db.Column(db.Integer, default=1)
    syllabus = db.Column(db.Text, default="")
    marks = db.Column(db.Float, default=0)
    percentile = db.Column(db.Float)
    rank = db.Column(db.Integer)
    correct = db.Column(db.Integer, default=0)
    incorrect = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    difficulty = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def attempted(self): return self.correct + self.incorrect
    @property
    def accuracy(self): return round(self.correct / self.attempted * 100, 1) if self.attempted else 0
    @property
    def percentage(self): return round(self.marks / self.max_marks * 100, 1) if self.max_marks else 0

class SubjectResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(36), db.ForeignKey("test.id"), nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    marks = db.Column(db.Float, default=0)
    correct = db.Column(db.Integer, default=0)
    incorrect = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    test = db.relationship("Test", backref=db.backref("subjects", cascade="all, delete-orphan"))

    @property
    def attempted(self): return self.correct + self.incorrect
    @property
    def accuracy(self): return round(self.correct / self.attempted * 100, 1) if self.attempted else 0

class DPP(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dpp_date = db.Column(db.Date, nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    chapter = db.Column(db.String(100), default="")
    number = db.Column(db.Integer, default=1)
    total = db.Column(db.Integer, default=0)
    attempted = db.Column(db.Integer, default=0)
    correct = db.Column(db.Integer, default=0)
    incorrect = db.Column(db.Integer, default=0)
    skipped = db.Column(db.Integer, default=0)
    time_minutes = db.Column(db.Integer, default=0)
    difficulty = db.Column(db.Integer, default=3)
    status = db.Column(db.String(30), default="Completed")

    @property
    def accuracy(self): return round(self.correct / self.attempted * 100, 1) if self.attempted else 0
    @property
    def score(self): return self.correct * 4 - self.incorrect
    @property
    def completion(self): return round(self.attempted / self.total * 100, 1) if self.total else 0

class Chapter(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subject = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(30), default="Not started")
    lectures = db.Column(db.Integer, default=0)
    total_lectures = db.Column(db.Integer, default=0)
    dpps = db.Column(db.Integer, default=0)
    questions = db.Column(db.Integer, default=0)
    accuracy = db.Column(db.Float, default=0)
    last_revised = db.Column(db.Date)
    confidence = db.Column(db.Integer, default=3)

class Mistake(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mistake_date = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(150), default="")
    subject = db.Column(db.String(20), nullable=False)
    chapter = db.Column(db.String(150), default="")
    question = db.Column(db.Text, default="")
    mistake_type = db.Column(db.String(50), default="Conceptual")
    explanation = db.Column(db.Text, default="")
    correct_approach = db.Column(db.Text, default="")
    difficulty = db.Column(db.Integer, default=3)

class Revision(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    revision_date = db.Column(db.Date, nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    chapter = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, default="")

class StudySession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_date = db.Column(db.Date, nullable=False)
    subject = db.Column(db.String(20), default="")
    minutes = db.Column(db.Integer, default=0)
    topic = db.Column(db.String(150), default="")

class Goal(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(150), nullable=False)
    target = db.Column(db.Float, default=0)
    current = db.Column(db.Float, default=0)
    unit = db.Column(db.String(30), default="")
    deadline = db.Column(db.Date)

def pct(a,b): return round(a/b*100,1) if b else 0
def avg(xs): return round(mean(xs),1) if xs else 0
def moving(xs, n=5): return round(mean(xs[-n:]),1) if xs else 0
def consistency(xs):
    if len(xs) < 2: return 100 if xs else 0
    sd = pstdev(xs)
    return round(max(0, 100 - sd / max(mean(xs),1) * 100),1)

def streak(dates):
    ds = {d for d in dates}
    cur = date.today()
    n = 0
    while cur in ds:
        n += 1
        cur -= timedelta(days=1)
    return n

def diagnosis(tests):
    if len(tests) < 2:
        return [{"severity":"info","title":"Build your baseline","text":"Add more tests to unlock meaningful performance diagnosis."}]
    recent = tests[-4:]
    older = tests[:-4] if len(tests)>4 else tests[:max(1,len(tests)-1)]
    ra, oa = avg([t.accuracy for t in recent]), avg([t.accuracy for t in older])
    rr, orate = avg([t.attempted/(t.attempted+t.skipped)*100 if t.attempted+t.skipped else 0 for t in recent]), avg([t.attempted/(t.attempted+t.skipped)*100 if t.attempted+t.skipped else 0 for t in older])
    out=[]
    if ra < oa-5: out.append({"severity":"high","title":"Accuracy is your bottleneck","text":f"Recent accuracy is {ra}% vs {oa}% previously. Increasing attempts without protecting accuracy will hurt your score."})
    if rr > orate+10 and ra < oa: out.append({"severity":"medium","title":"Attempt rate is rising faster than accuracy","text":f"Attempt rate rose to {rr}% while accuracy moved down. Prioritize selection and question quality."})
    if len(tests)>=4 and consistency([t.marks for t in tests]) < 60: out.append({"severity":"medium","title":"Performance is inconsistent","text":"Your score spread is large. Track test difficulty and focus on repeatable execution rather than one-off highs."})
    if not out: out.append({"severity":"good","title":"No major red flag detected","text":"Your recent metrics are not showing a major deterioration. Keep collecting clean test data."})
    return out

@app.route("/")
def home(): return render_template("dashboard.html")

@app.route("/<page>")
def page(page):
    allowed={"dashboard","tests","dpp","chapters","mistakes","revision","analytics","review","goals","calendar","settings"}
    if page not in allowed: return render_template("dashboard.html")
    return render_template(f"{page}.html")

@app.get("/api/dashboard")
def dashboard():
    tests=Test.query.order_by(Test.test_date).all()
    dpps=DPP.query.order_by(DPP.dpp_date).all()
    chapters=Chapter.query.all()
    activities=set([t.test_date for t in tests]+[d.dpp_date for d in dpps]+[r.revision_date for r in Revision.query.all()]+[s.session_date for s in StudySession.query.all()])
    scores=[t.marks for t in tests]
    return jsonify({
        "kpis":{"latest_score":tests[-1].marks if tests else 0,"best_score":max(scores) if scores else 0,"avg_score":avg(scores),"latest_percentile":tests[-1].percentile if tests else 0,"best_percentile":max([t.percentile or 0 for t in tests],default=0),"accuracy":avg([t.accuracy for t in tests]),"tests":len(tests),"questions":sum(t.attempted+t.skipped for t in tests),"correct":sum(t.correct for t in tests),"incorrect":sum(t.incorrect for t in tests),"skipped":sum(t.skipped for t in tests),"dpps":len(dpps),"streak":streak(activities),"chapters_done":sum(c.status=="Completed" for c in chapters),"chapters_running":sum(c.status=="Running" for c in chapters),"backlogs":sum(c.status=="Not started" for c in chapters)},
        "tests":[{"date":t.test_date.isoformat(),"name":t.name,"marks":t.marks,"accuracy":t.accuracy,"difficulty":t.difficulty} for t in tests],
        "subjects":{s:{"avg":avg([r.marks for t in tests for r in t.subjects if r.subject==s]),"accuracy":avg([r.accuracy for t in tests for r in t.subjects if r.subject==s])} for s in ["Physics","Chemistry","Mathematics"]},
        "diagnosis":diagnosis(tests),
        "weak":[{"name":c.name,"subject":c.subject,"accuracy":c.accuracy,"confidence":c.confidence} for c in sorted(chapters,key=lambda c:(c.accuracy,c.confidence))[:5]],
        "revision":[{"chapter":c.name,"subject":c.subject,"days":(date.today()-c.last_revised).days if c.last_revised else 999,"accuracy":c.accuracy} for c in chapters if c.status in ("Completed","Revision needed","Weak")],
        "records":{"score":max(scores,default=0),"accuracy":max([t.accuracy for t in tests],default=0),"physics":max([r.marks for t in tests for r in t.subjects if r.subject=="Physics"],default=0),"chemistry":max([r.marks for t in tests for r in t.subjects if r.subject=="Chemistry"],default=0),"mathematics":max([r.marks for t in tests for r in t.subjects if r.subject=="Mathematics"],default=0)}
    })

@app.route("/api/tests",methods=["GET","POST"])
def tests_api():
    if request.method=="GET":
        return jsonify([test_json(t) for t in Test.query.order_by(Test.test_date.desc()).all()])
    x=request.json
    t=Test(name=x["name"],test_date=date.fromisoformat(x["date"]),test_type=x.get("type","Custom"),max_marks=float(x.get("max_marks",300)),duration=int(x.get("duration",180)),attempt=int(x.get("attempt",1)),syllabus=x.get("syllabus",""),marks=float(x.get("marks",0)),percentile=float(x["percentile"]) if x.get("percentile") not in ("",None) else None,rank=int(x["rank"]) if x.get("rank") not in ("",None) else None,correct=int(x.get("correct",0)),incorrect=int(x.get("incorrect",0)),skipped=int(x.get("skipped",0)),difficulty=int(x.get("difficulty",3)))
    db.session.add(t); db.session.flush()
    for s in ["Physics","Chemistry","Mathematics"]:
        z=x.get("subjects",{}).get(s,{})
        db.session.add(SubjectResult(test_id=t.id,subject=s,marks=float(z.get("marks",0)),correct=int(z.get("correct",0)),incorrect=int(z.get("incorrect",0)),skipped=int(z.get("skipped",0))))
    db.session.commit()
    return jsonify(test_json(t)),201

def test_json(t):
    return {"id":t.id,"name":t.name,"date":t.test_date.isoformat(),"type":t.test_type,"marks":t.marks,"max_marks":t.max_marks,"percentile":t.percentile,"rank":t.rank,"accuracy":t.accuracy,"correct":t.correct,"incorrect":t.incorrect,"skipped":t.skipped,"difficulty":t.difficulty,"subjects":[{"subject":r.subject,"marks":r.marks,"correct":r.correct,"incorrect":r.incorrect,"skipped":r.skipped,"accuracy":r.accuracy} for r in t.subjects]}

@app.post("/api/dpp")
def dpp_api():
    x=request.json; d=DPP(dpp_date=date.fromisoformat(x["date"]),subject=x["subject"],chapter=x.get("chapter",""),number=int(x.get("number",1)),total=int(x.get("total",0)),attempted=int(x.get("attempted",0)),correct=int(x.get("correct",0)),incorrect=int(x.get("incorrect",0)),skipped=int(x.get("skipped",0)),time_minutes=int(x.get("time",0)),difficulty=int(x.get("difficulty",3)),status=x.get("status","Completed"))
    db.session.add(d); db.session.commit(); return jsonify({"id":d.id}),201

@app.get("/api/dpp")
def dpp_list(): return jsonify([{"id":d.id,"date":d.dpp_date.isoformat(),"subject":d.subject,"chapter":d.chapter,"number":d.number,"total":d.total,"attempted":d.attempted,"correct":d.correct,"incorrect":d.incorrect,"skipped":d.skipped,"accuracy":d.accuracy,"score":d.score,"status":d.status} for d in DPP.query.order_by(DPP.dpp_date.desc()).all()])

@app.post("/api/chapters")
def chapter_api():
    x=request.json; c=Chapter(subject=x["subject"],name=x["name"],status=x.get("status","Not started"),lectures=int(x.get("lectures",0)),total_lectures=int(x.get("total_lectures",0)),dpps=int(x.get("dpps",0)),questions=int(x.get("questions",0)),accuracy=float(x.get("accuracy",0)),last_revised=date.fromisoformat(x["last_revised"]) if x.get("last_revised") else None,confidence=int(x.get("confidence",3)))
    db.session.add(c); db.session.commit(); return jsonify({"id":c.id}),201

@app.get("/api/chapters")
def chapters_api(): return jsonify([{"id":c.id,"subject":c.subject,"name":c.name,"status":c.status,"lectures":c.lectures,"total_lectures":c.total_lectures,"dpps":c.dpps,"questions":c.questions,"accuracy":c.accuracy,"last_revised":c.last_revised.isoformat() if c.last_revised else None,"confidence":c.confidence} for c in Chapter.query.all()])

@app.post("/api/mistakes")
def mistake_api():
    x=request.json; m=Mistake(mistake_date=date.fromisoformat(x["date"]),source=x.get("source",""),subject=x["subject"],chapter=x.get("chapter",""),question=x.get("question",""),mistake_type=x.get("type","Conceptual"),explanation=x.get("explanation",""),correct_approach=x.get("approach",""),difficulty=int(x.get("difficulty",3)))
    db.session.add(m); db.session.commit(); return jsonify({"id":m.id}),201

@app.get("/api/mistakes")
def mistakes_api(): return jsonify([{"id":m.id,"date":m.mistake_date.isoformat(),"source":m.source,"subject":m.subject,"chapter":m.chapter,"type":m.mistake_type,"explanation":m.explanation} for m in Mistake.query.order_by(Mistake.mistake_date.desc()).all()])

@app.post("/api/revision")
def revision_api():
    x=request.json; r=Revision(revision_date=date.fromisoformat(x["date"]),subject=x["subject"],chapter=x["chapter"],notes=x.get("notes",""))
    db.session.add(r); db.session.commit()
    c=Chapter.query.filter_by(name=x["chapter"],subject=x["subject"]).first()
    if c: c.last_revised=r.revision_date
    db.session.commit(); return jsonify({"id":r.id}),201

@app.get("/api/revision")
def revision_api_get(): return jsonify([{"id":r.id,"date":r.revision_date.isoformat(),"subject":r.subject,"chapter":r.chapter} for r in Revision.query.order_by(Revision.revision_date.desc()).all()])


@app.put("/api/tests/<test_id>")
def update_test(test_id):
    t = Test.query.get_or_404(test_id); x=request.json
    t.name=x["name"]; t.test_date=date.fromisoformat(x["date"]); t.test_type=x.get("type","Custom")
    t.max_marks=float(x.get("max_marks",300)); t.duration=int(x.get("duration",180)); t.attempt=int(x.get("attempt",1)); t.syllabus=x.get("syllabus","")
    t.marks=float(x.get("marks",0)); t.percentile=float(x["percentile"]) if x.get("percentile") not in ("",None) else None
    t.rank=int(x["rank"]) if x.get("rank") not in ("",None) else None; t.correct=int(x.get("correct",0)); t.incorrect=int(x.get("incorrect",0)); t.skipped=int(x.get("skipped",0)); t.difficulty=int(x.get("difficulty",3))
    for r in t.subjects:
        z=x.get("subjects",{}).get(r.subject,{})
        r.marks=float(z.get("marks",0)); r.correct=int(z.get("correct",0)); r.incorrect=int(z.get("incorrect",0)); r.skipped=int(z.get("skipped",0))
    db.session.commit(); return jsonify(test_json(t))

@app.delete("/api/tests/<test_id>")
def delete_test(test_id):
    t=Test.query.get_or_404(test_id); db.session.delete(t); db.session.commit(); return jsonify({"ok":True})

@app.put("/api/dpp/<dpp_id>")
def update_dpp(dpp_id):
    d=DPP.query.get_or_404(dpp_id); x=request.json
    d.dpp_date=date.fromisoformat(x["date"]); d.subject=x["subject"]; d.chapter=x.get("chapter",""); d.number=int(x.get("number",1)); d.total=int(x.get("total",0)); d.attempted=int(x.get("attempted",0)); d.correct=int(x.get("correct",0)); d.incorrect=int(x.get("incorrect",0)); d.skipped=int(x.get("skipped",0)); d.time_minutes=int(x.get("time",0)); d.difficulty=int(x.get("difficulty",3)); d.status=x.get("status","Completed")
    db.session.commit(); return jsonify({"ok":True})

@app.delete("/api/dpp/<dpp_id>")
def delete_dpp(dpp_id):
    d=DPP.query.get_or_404(dpp_id); db.session.delete(d); db.session.commit(); return jsonify({"ok":True})

@app.put("/api/chapters/<chapter_id>")
def update_chapter(chapter_id):
    c=Chapter.query.get_or_404(chapter_id); x=request.json
    old_subject, old_name = c.subject, c.name
    c.subject=x["subject"]; c.name=x["name"]; c.status=x.get("status","Not started"); c.lectures=int(x.get("lectures",0)); c.total_lectures=int(x.get("total_lectures",0)); c.dpps=int(x.get("dpps",0)); c.questions=int(x.get("questions",0)); c.accuracy=float(x.get("accuracy",0)); c.last_revised=date.fromisoformat(x["last_revised"]) if x.get("last_revised") else None; c.confidence=int(x.get("confidence",3))
    # Keep the relationship intact if a chapter is renamed or its subject changes.
    for d in DPP.query.filter_by(subject=old_subject, chapter=old_name).all():
        d.subject = c.subject
        d.chapter = c.name
    db.session.commit(); return jsonify({"ok":True})

@app.delete("/api/chapters/<chapter_id>")
def delete_chapter(chapter_id):
    c=Chapter.query.get_or_404(chapter_id)
    # Never delete historical DPP data. Detach it from the chapter instead.
    for d in DPP.query.filter_by(subject=c.subject, chapter=c.name).all():
        d.chapter = ""
    db.session.delete(c); db.session.commit(); return jsonify({"ok":True})

@app.put("/api/mistakes/<mistake_id>")
def update_mistake(mistake_id):
    m=Mistake.query.get_or_404(mistake_id); x=request.json
    m.mistake_date=date.fromisoformat(x["date"]); m.source=x.get("source",""); m.subject=x["subject"]; m.chapter=x.get("chapter",""); m.question=x.get("question",""); m.mistake_type=x.get("type","Conceptual"); m.explanation=x.get("explanation",""); m.correct_approach=x.get("approach",""); m.difficulty=int(x.get("difficulty",3))
    db.session.commit(); return jsonify({"ok":True})

@app.delete("/api/mistakes/<mistake_id>")
def delete_mistake(mistake_id):
    m=Mistake.query.get_or_404(mistake_id); db.session.delete(m); db.session.commit(); return jsonify({"ok":True})

@app.put("/api/revision/<revision_id>")
def update_revision(revision_id):
    r=Revision.query.get_or_404(revision_id); x=request.json; r.revision_date=date.fromisoformat(x["date"]); r.subject=x["subject"]; r.chapter=x["chapter"]; r.notes=x.get("notes",""); db.session.commit(); return jsonify({"ok":True})

@app.delete("/api/revision/<revision_id>")
def delete_revision(revision_id):
    r=Revision.query.get_or_404(revision_id); db.session.delete(r); db.session.commit(); return jsonify({"ok":True})

@app.put("/api/goals/<goal_id>")
def update_goal(goal_id):
    g=Goal.query.get_or_404(goal_id); x=request.json; g.name=x["name"]; g.target=float(x["target"]); g.current=float(x.get("current",0)); g.unit=x.get("unit",""); g.deadline=date.fromisoformat(x["deadline"]) if x.get("deadline") else None; db.session.commit(); return jsonify({"ok":True})

@app.delete("/api/goals/<goal_id>")
def delete_goal(goal_id):
    g=Goal.query.get_or_404(goal_id); db.session.delete(g); db.session.commit(); return jsonify({"ok":True})

@app.get("/api/dpp/imported-snapshot")
def dpp_imported_snapshot():
    con = sqlite3.connect(BASE / "jee_tracker.db")
    con.row_factory = sqlite3.Row
    snap = con.execute("SELECT * FROM dpp_import_snapshot ORDER BY id DESC LIMIT 1").fetchone()
    if not snap:
        con.close(); return jsonify(None)
    subjects = con.execute("SELECT * FROM dpp_import_snapshot_subject WHERE snapshot_id=? ORDER BY id", (snap["id"],)).fetchall()
    con.close()
    return jsonify({
        "source": snap["source"], "imported_at": snap["imported_at"],
        "planned_dpps": snap["planned_dpps"], "completed_dpps": snap["completed_dpps"],
        "total_questions": snap["total_questions"], "attempted_questions": snap["attempted_questions"],
        "correct_questions": snap["correct_questions"],
        "accuracy": pct(snap["correct_questions"], snap["attempted_questions"]),
        "subjects": [dict(x) for x in subjects]
    })

@app.get("/api/dpp/analytics")
def dpp_analytics():
    dpps=DPP.query.order_by(DPP.dpp_date).all(); by_subject={}; by_day={}; by_chapter={}
    for d in dpps:
        s=by_subject.setdefault(d.subject,{"dpps":0,"questions":0,"correct":0,"attempted":0}); s["dpps"]+=1; s["questions"]+=d.total; s["correct"]+=d.correct; s["attempted"]+=d.attempted
        k=d.dpp_date.isoformat(); q=by_day.setdefault(k,{"dpps":0,"questions":0,"correct":0,"attempted":0}); q["dpps"]+=1; q["questions"]+=d.attempted; q["correct"]+=d.correct; q["attempted"]+=d.attempted
        c=by_chapter.setdefault(d.chapter or "Unassigned",{"dpps":0,"attempted":0,"correct":0}); c["dpps"]+=1; c["attempted"]+=d.attempted; c["correct"]+=d.correct
    total=sum(d.total for d in dpps); attempted=sum(d.attempted for d in dpps); completed=sum(d.status in ("Completed","Reattempted") for d in dpps)
    return jsonify({"summary":{"dpps":len(dpps),"completed":completed,"completion":pct(completed,len(dpps)),"questions":total,"attempted":attempted,"accuracy":pct(sum(d.correct for d in dpps),attempted),"avg_time":round(sum(d.time_minutes for d in dpps)/attempted,2) if attempted else 0},"subject":[{"subject":k,**v,"accuracy":pct(v["correct"],v["attempted"])} for k,v in by_subject.items()],"daily":[{"date":k,**v,"accuracy":pct(v["correct"],v["attempted"])} for k,v in sorted(by_day.items())],"chapters":[{"chapter":k,**v,"accuracy":pct(v["correct"],v["attempted"])} for k,v in sorted(by_chapter.items(),key=lambda z:z[1]["attempted"],reverse=True)]})

@app.get("/api/analytics")
def analytics():
    tests=Test.query.order_by(Test.test_date).all()
    scores=[t.marks for t in tests]
    return jsonify({"average":avg(scores),"median":round(median(scores),1) if scores else 0,"best":max(scores,default=0),"worst":min(scores,default=0),"sd":round(pstdev(scores),1) if len(scores)>1 else 0,"consistency":consistency(scores),"moving_average":moving(scores),"tests":[{"date":t.test_date.isoformat(),"score":t.marks,"accuracy":t.accuracy,"difficulty":t.difficulty} for t in tests]})

@app.post("/api/goals")
def goal_api():
    x=request.json; g=Goal(name=x["name"],target=float(x["target"]),current=float(x.get("current",0)),unit=x.get("unit",""),deadline=date.fromisoformat(x["deadline"]) if x.get("deadline") else None)
    db.session.add(g); db.session.commit(); return jsonify({"id":g.id}),201

@app.get("/api/goals")
def goals_api(): return jsonify([{"id":g.id,"name":g.name,"target":g.target,"current":g.current,"unit":g.unit,"deadline":g.deadline.isoformat() if g.deadline else None,"progress":min(100,pct(g.current,g.target))} for g in Goal.query.all()])

@app.get("/api/export")
def export_api():
    data={t.__tablename__:[] for t in [Test,DPP,Chapter,Mistake,Revision,StudySession,Goal]}
    for model in [Test,DPP,Chapter,Mistake,Revision,StudySession,Goal]:
        for obj in model.query.all():
            row={c.name:getattr(obj,c.name) for c in model.__table__.columns}
            for k,v in row.items():
                if isinstance(v,(date,datetime)): row[k]=v.isoformat()
            data[model.__tablename__].append(row)
    return jsonify(data)

@app.post("/api/import")
def import_api():
    data=request.json
    # Safe/simple backup restore: wipe only after explicit client confirmation.
    db.drop_all(); db.create_all()
    for row in data.get("test",[]):
        row=dict(row); row["test_date"]=date.fromisoformat(row["test_date"]); row.pop("id",None); row.pop("created_at",None)
        db.session.add(Test(**row))
    db.session.commit()
    return jsonify({"ok":True})

@app.post("/api/demo")
def demo_api():
    db.drop_all(); db.create_all()
    today=date.today()
    chapters=[("Physics","Units & Measurements","Completed",3,3,10,120,82),("Physics","Motion in Straight Line","Running",8,20,6,75,54),("Chemistry","Mole Concept","Completed",12,12,10,180,73),("Mathematics","Trigonometry","Running",10,24,7,130,48),("Mathematics","Sets","Completed",8,8,8,100,88)]
    for s,n,st,l,tl,d,q,a in chapters: db.session.add(Chapter(subject=s,name=n,status=st,lectures=l,total_lectures=tl,dpps=d,questions=q,accuracy=a,last_revised=today-timedelta(days=(2 if st=="Completed" else 12)),confidence=4 if a>70 else 2))
    for i in range(10):
        d=today-timedelta(days=27-i*3); marks=45+i*5+(i%3)*4
        t=Test(name=f"Practice Test {i+1}",test_date=d,test_type="Coaching test",max_marks=300,marks=marks,percentile=55+i*2,correct=10+i,incorrect=5,skipped=0)
        t.skipped=max(0,30-t.correct-t.incorrect); t.difficulty=2+(i%4)
        db.session.add(t); db.session.flush()
        vals=[("Physics",marks*.34,4+i//3,2,3),("Chemistry",marks*.33,4+i//2,2,3),("Mathematics",marks*.33,2+i//2,3,5)]
        for s,m,c,inc,sk in vals: db.session.add(SubjectResult(test_id=t.id,subject=s,marks=m,correct=c,incorrect=inc,skipped=sk))
    for i in range(24):
        d=today-timedelta(days=i)
        db.session.add(DPP(dpp_date=d,subject=["Physics","Chemistry","Mathematics"][i%3],chapter=chapters[i%5][1],number=i%12+1,total=20,attempted=16+(i%5),correct=12+(i%4),incorrect=4,skipped=0,time_minutes=30+i%15,status="Completed"))
    for i,typ in enumerate(["Conceptual","Calculation","Silly mistake","Formula forgotten","Misread question","Didn't know"]*4):
        db.session.add(Mistake(mistake_date=today-timedelta(days=i%18),source=f"Test {i%5+1}",subject=["Physics","Chemistry","Mathematics"][i%3],chapter=chapters[i%5][1],mistake_type=typ,question="Demo question",explanation="Demo record",correct_approach="Review and re-solve"))
    db.session.commit(); return jsonify({"ok":True})

@app.post("/api/reset")
def reset_api():
    db.drop_all(); db.create_all(); return jsonify({"ok":True})

with app.app_context():
    db.create_all()

if __name__=="__main__":
    app.run(debug=True)
