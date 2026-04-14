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
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

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

def read_db(conn, lock=False):
    """Read current data from DB. Pass lock=True to acquire a row-level lock."""
    with conn.cursor() as cur:
        sql = "SELECT data FROM store WHERE id = 1"
        if lock:
            sql += " FOR UPDATE"
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else {'activeTeamId': None, 'teams': []}

def write_db(conn, data):
    """Write data to DB (must be inside a transaction with lock held)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE store SET data = %s WHERE id = 1",
            [psycopg2.extras.Json(data)]
        )

def file_load():
    if os.path.exists('data.json'):
        try:
            with open('data.json') as f:
                return json.load(f)
        except Exception:
            pass
    return {'activeTeamId': None, 'teams': []}

def file_save(data):
    with open('data.json', 'w') as f:
        json.dump(data, f)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    """Always reads fresh from DB — no stale in-memory cache."""
    if DATABASE_URL:
        try:
            with get_db() as conn:
                data = read_db(conn)
                backfill_ids(data)
                return jsonify(data)
        except Exception as e:
            print(f"GET error: {e}")
            return jsonify({'activeTeamId': None, 'teams': []}), 500
    else:
        return jsonify(file_load())

@app.route('/api/data', methods=['POST'])
def set_data():
    """Bulk save for admin operations (team management, adding/removing members).
    Uses a row-level lock to prevent concurrent bulk writes clobbering each other."""
    incoming = request.get_json()
    if DATABASE_URL:
        try:
            with get_db() as conn:
                read_db(conn, lock=True)   # acquire lock, discard value
                write_db(conn, incoming)
            return '', 204
        except Exception as e:
            print(f"POST error: {e}")
            return '', 500
    else:
        file_save(incoming)
        return '', 204

@app.route('/api/members/<member_id>', methods=['PUT'])
def update_member(member_id):
    """Granular save for a single member's songs.
    Reads the latest DB state, patches just this member, writes back atomically.
    Prevents one person's save from overwriting another person's concurrent save."""
    payload = request.get_json()
    if DATABASE_URL:
        try:
            with get_db() as conn:
                data = read_db(conn, lock=True)   # lock row before patching
                for team in data.get('teams', []):
                    for i, m in enumerate(team.get('members', [])):
                        if m['id'] == member_id:
                            team['members'][i] = {
                                **m,
                                'name':  payload.get('name',  m['name']),
                                'songs': payload.get('songs', m['songs']),
                            }
                            write_db(conn, data)
                            return jsonify(team['members'][i])
            return '', 404
        except Exception as e:
            print(f"PUT member error: {e}")
            return '', 500
    else:
        # Local fallback
        data = file_load()
        for team in data.get('teams', []):
            for i, m in enumerate(team.get('members', [])):
                if m['id'] == member_id:
                    team['members'][i] = {
                        **m,
                        'name':  payload.get('name',  m['name']),
                        'songs': payload.get('songs', m['songs']),
                    }
                    file_save(data)
                    return jsonify(team['members'][i])
        return '', 404

if __name__ == '__main__':
    if DATABASE_URL:
        init_db()
    port = int(os.environ.get('PORT', 3456))
    app.run(host='0.0.0.0', port=port, debug=False)
