import json
import os
import secrets
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

# ── DB connection ─────────────────────────────────────────────────────────────
_conn = None

def get_db():
    global _conn
    try:
        if _conn is None or _conn.closed:
            _conn = psycopg2.connect(DATABASE_URL)
        # test the connection is still alive
        _conn.cursor().execute('SELECT 1')
        return _conn
    except Exception:
        _conn = psycopg2.connect(DATABASE_URL)
        return _conn

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS store (
                    id INTEGER PRIMARY KEY,
                    data JSONB NOT NULL
                )
            """)
            cur.execute("""
                INSERT INTO store (id, data)
                VALUES (1, '{"activeTeamId": null, "teams": []}')
                ON CONFLICT (id) DO NOTHING
            """)

# ── Helpers ───────────────────────────────────────────────────────────────────
def backfill_ids(data):
    changed = False
    for team in data.get('teams', []):
        for member in team.get('members', []):
            if 'id' not in member:
                member['id'] = secrets.token_urlsafe(6)
                changed = True
    return changed

# ── Load / save ───────────────────────────────────────────────────────────────
def load():
    if DATABASE_URL:
        try:
            init_db()
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM store WHERE id = 1")
                    row = cur.fetchone()
                    if row:
                        data = row[0]  # psycopg2 auto-parses JSONB to dict
                        if backfill_ids(data):
                            save(data)
                        return data
        except Exception as e:
            print(f"DB load error: {e}")
    else:
        # Local fallback: file-based storage
        if os.path.exists('data.json'):
            try:
                with open('data.json') as f:
                    data = json.load(f)
                if backfill_ids(data):
                    save(data)
                return data
            except Exception as e:
                print(f"File load error: {e}")

    return {'activeTeamId': None, 'teams': []}

def save(data):
    if DATABASE_URL:
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE store SET data = %s WHERE id = 1",
                        [psycopg2.extras.Json(data)]
                    )
        except Exception as e:
            print(f"DB save error: {e}")
    else:
        try:
            with open('data.json', 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"File save error: {e}")

store = load()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(store)

@app.route('/api/data', methods=['POST'])
def set_data():
    global store
    store = request.get_json()
    save(store)
    return '', 204

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3456))
    app.run(host='0.0.0.0', port=port, debug=False)
