"""
us — the private version.

Login-gated. Notes persist and are attributed. Photos live in our own
database (behind the password), with the image files stored on Cloudinary.

Locally it uses a SQLite file (us.db) so you can just run it.
In production, set DATABASE_URL to a Postgres URL so nothing is lost on redeploy.
See DEPLOY.md.
"""

import os
import re
from datetime import datetime, timezone
from functools import wraps
from secrets import token_urlsafe

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# load a local .env if present (no-op in production)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# ── config ──────────────────────────────────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

db_url = os.environ.get("DATABASE_URL", "sqlite:///us.db")
if db_url.startswith("postgres://"):                 # Render/Heroku style → SQLAlchemy style
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

IN_PROD = os.environ.get("FLASK_ENV") != "development"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IN_PROD,   # cookie only sent over HTTPS in production
)

db = SQLAlchemy(app)


# ── models ──────────────────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    pw_hash = db.Column(db.String(255), nullable=False)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(80), nullable=False)
    created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(255))
    caption = db.Column(db.String(280), default="")
    author = db.Column(db.String(80), nullable=False)
    created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)      # track / album / playlist / episode / show
    sid = db.Column(db.String(64), nullable=False)       # the spotify id
    note = db.Column(db.String(280), default="")
    author = db.Column(db.String(80), nullable=False)
    created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Media(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False)      # photo / video / audio
    url = db.Column(db.String(500), nullable=False)
    public_id = db.Column(db.String(255))
    caption = db.Column(db.String(280), default="")
    author = db.Column(db.String(80), nullable=False)
    created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ── helpers ─────────────────────────────────────────────────────────
def current_user():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if not current_user():
            if request.path.startswith("/api/"):
                abort(401)
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return wrap


def csrf_token():
    tok = session.get("csrf")
    if not tok:
        tok = token_urlsafe(32)
        session["csrf"] = tok
    return tok


def check_csrf():
    body = request.get_json(silent=True) or {}
    sent = request.headers.get("X-CSRF") or body.get("csrf")
    if not sent or sent != session.get("csrf"):
        abort(403)


# Accepts open.spotify.com links (with optional /intl-xx/ locale) and spotify: URIs.
SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?|spotify:)"
    r"(track|album|playlist|episode|show)[/:]([A-Za-z0-9]+)"
)


def parse_spotify(link):
    """Return (kind, id) from a Spotify link/URI, or (None, None)."""
    if not link:
        return None, None
    m = SPOTIFY_RE.search(link.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


def seed_users():
    """Create the two of you from env vars, once. Won't overwrite existing."""
    pairs = [
        (os.environ.get("USER1_NAME"), os.environ.get("USER1_PASS")),
        (os.environ.get("USER2_NAME"), os.environ.get("USER2_PASS")),
    ]
    changed = False
    for name, pw in pairs:
        if name and pw and not User.query.filter_by(name=name).first():
            db.session.add(User(name=name, pw_hash=generate_password_hash(pw)))
            changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()   # harmless race between gunicorn workers


with app.app_context():
    db.create_all()
    seed_users()


# ── pages ───────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("home"))
    error = None
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        pw = request.form.get("password") or ""
        u = User.query.filter_by(name=name).first()
        if u and check_password_hash(u.pw_hash, pw):
            session.clear()
            session["uid"] = u.id
            nxt = request.args.get("next") or url_for("home")
            return redirect(nxt if nxt.startswith("/") else url_for("home"))
        error = "That name and password don't match."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    u = current_user()
    return render_template("index.html", user_name=u.name, csrf=csrf_token())


# ── notes API ───────────────────────────────────────────────────────
def note_json(n):
    return {"id": n.id, "body": n.body, "author": n.author,
            "created": n.created.isoformat()}


@app.get("/api/notes")
@login_required
def notes_list():
    rows = Note.query.order_by(Note.created.desc()).all()
    return jsonify([note_json(n) for n in rows])


@app.post("/api/notes")
@login_required
def notes_add():
    check_csrf()
    body = ((request.get_json(silent=True) or {}).get("body") or "").strip()
    if not body:
        abort(400)
    n = Note(body=body[:2000], author=current_user().name)
    db.session.add(n)
    db.session.commit()
    return jsonify(note_json(n)), 201


@app.post("/api/notes/<int:nid>/delete")
@login_required
def notes_del(nid):
    check_csrf()
    n = db.session.get(Note, nid)
    if n:
        db.session.delete(n)
        db.session.commit()
    return ("", 204)


# ── photos API ──────────────────────────────────────────────────────
def photo_json(p):
    return {"id": p.id, "url": p.url, "caption": p.caption, "author": p.author,
            "created": p.created.isoformat()}


@app.get("/api/photos")
@login_required
def photos_list():
    rows = Photo.query.order_by(Photo.created.desc()).all()
    return jsonify([photo_json(p) for p in rows])


@app.post("/api/photos")
@login_required
def photos_add():
    check_csrf()
    d = request.get_json(silent=True) or {}
    url = (d.get("url") or "").strip()
    if not url.startswith("https://"):
        abort(400)
    p = Photo(url=url[:500],
              public_id=(d.get("public_id") or "")[:255],
              caption=(d.get("caption") or "")[:280],
              author=current_user().name)
    db.session.add(p)
    db.session.commit()
    return jsonify(photo_json(p)), 201


@app.post("/api/photos/<int:pid>/delete")
@login_required
def photos_del(pid):
    check_csrf()
    p = db.session.get(Photo, pid)
    if p:
        db.session.delete(p)
        db.session.commit()
    return ("", 204)


# ── media API (photos / video / audio) ──────────────────────────────
MEDIA_KINDS = {"photo", "video", "audio"}


def media_json(m):
    return {"id": m.id, "kind": m.kind, "url": m.url, "caption": m.caption,
            "author": m.author, "created": m.created.isoformat()}


@app.get("/api/media")
@login_required
def media_list():
    kind = request.args.get("kind")
    q = Media.query
    if kind in MEDIA_KINDS:
        q = q.filter_by(kind=kind)
    rows = q.order_by(Media.created.desc()).all()
    return jsonify([media_json(m) for m in rows])


@app.post("/api/media")
@login_required
def media_add():
    check_csrf()
    d = request.get_json(silent=True) or {}
    kind = d.get("kind")
    url = (d.get("url") or "").strip()
    if kind not in MEDIA_KINDS or not url.startswith("https://"):
        abort(400)
    m = Media(kind=kind, url=url[:500],
              public_id=(d.get("public_id") or "")[:255],
              caption=(d.get("caption") or "")[:280],
              author=current_user().name)
    db.session.add(m)
    db.session.commit()
    return jsonify(media_json(m)), 201


@app.post("/api/media/<int:mid>/delete")
@login_required
def media_del(mid):
    check_csrf()
    m = db.session.get(Media, mid)
    if m:
        db.session.delete(m)
        db.session.commit()
    return ("", 204)


# ── songs API (shared playlist) ─────────────────────────────────────
def song_json(s):
    return {"id": s.id, "kind": s.kind, "sid": s.sid, "note": s.note,
            "author": s.author, "created": s.created.isoformat()}


@app.get("/api/songs")
@login_required
def songs_list():
    rows = Song.query.order_by(Song.created.desc()).all()
    return jsonify([song_json(s) for s in rows])


@app.post("/api/songs")
@login_required
def songs_add():
    check_csrf()
    d = request.get_json(silent=True) or {}
    kind, sid = parse_spotify(d.get("link"))
    if not kind:
        return jsonify({"error": "That doesn't look like a Spotify link."}), 400
    s = Song(kind=kind, sid=sid, note=(d.get("note") or "")[:280],
             author=current_user().name)
    db.session.add(s)
    db.session.commit()
    return jsonify(song_json(s)), 201


@app.post("/api/songs/<int:sid>/delete")
@login_required
def songs_del(sid):
    check_csrf()
    s = db.session.get(Song, sid)
    if s:
        db.session.delete(s)
        db.session.commit()
    return ("", 204)


if __name__ == "__main__":
    # Cloud Shell exposes port 8080 via Web Preview
    app.run(host="0.0.0.0", port=8080, debug=True)
