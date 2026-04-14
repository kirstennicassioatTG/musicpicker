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
if not DATABASE_URL:
    print("WARNING: DATABASE_URL not set — using local data.json (data will not persist on Railway)")

PREDEFINED_TEAMS = sorted([
    'Dogs', 'Foxes', 'Lions', 'Monarchs', 'Mustangs',
    'Otters', 'Penguins', 'Phoenix', 'Rams', 'Raptors', 'Tigers',
])

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    return psycopg2.connect(DATABASE_URL)

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
                VALUES (1, '{"teams": []}')
                ON CONFLICT (id) DO NOTHING
            """)
        seed_teams(conn)

def seed_teams(conn):
    """Ensure every predefined team exists; add missing ones, leave existing ones alone."""
    data = read_db(conn, lock=True)
    existing_names = {t['name'] for t in data.get('teams', [])}
    changed = False
    for name in PREDEFINED_TEAMS:
        if name not in existing_names:
            data['teams'].append({'id': secrets.token_urlsafe(6), 'name': name, 'members': []})
            changed = True
    # Sort teams alphabetically
    data['teams'].sort(key=lambda t: t['name'])
    if changed:
        write_db(conn, data)

def read_db(conn, lock=False):
    with conn.cursor() as cur:
        cur.execute("SELECT data FROM store WHERE id = 1" + (" FOR UPDATE" if lock else ""))
        row = cur.fetchone()
        return row[0] if row else {'teams': []}

def write_db(conn, data):
    with conn.cursor() as cur:
        cur.execute("UPDATE store SET data = %s WHERE id = 1", [psycopg2.extras.Json(data)])

def empty_songs():
    songs = [{'title': '', 'url': ''} for _ in range(5)]
    songs[0] = {'title': 'Default', 'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ&start_radio=1'}
    return songs

# ── Local file fallback (no DATABASE_URL) ─────────────────────────────────────
def file_load():
    if os.path.exists('data.json'):
        try:
            with open('data.json') as f:
                data = json.load(f)
                # Seed predefined teams into file store too
                existing_names = {t['name'] for t in data.get('teams', [])}
                for name in PREDEFINED_TEAMS:
                    if name not in existing_names:
                        data['teams'].append({'id': secrets.token_urlsafe(6), 'name': name, 'members': []})
                data['teams'].sort(key=lambda t: t['name'])
                return data
        except Exception:
            pass
    # Fresh file: seed all predefined teams
    data = {'teams': [{'id': secrets.token_urlsafe(6), 'name': n, 'members': []} for n in PREDEFINED_TEAMS]}
    file_save(data)
    return data

def file_save(data):
    with open('data.json', 'w') as f:
        json.dump(data, f)

# Run at module load so gunicorn picks it up (not just `python server.py`)
if DATABASE_URL:
    try:
        init_db()
        print("DB initialised OK")
    except Exception as e:
        print(f"init_db failed: {e}")

def with_data(fn):
    """Read, mutate via fn(data), write back atomically. Works for both DB and file."""
    if DATABASE_URL:
        with get_db() as conn:
            data = read_db(conn, lock=True)
            result = fn(data)
            write_db(conn, data)
            return result
    else:
        data = file_load()
        result = fn(data)
        file_save(data)
        return result

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
@app.route('/<path:team_slug>')
def index(team_slug=None):
    return send_from_directory('.', 'index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    if DATABASE_URL:
        try:
            with get_db() as conn:
                return jsonify(read_db(conn))
        except Exception as e:
            print(f"GET error: {e}")
            return jsonify({'teams': []}), 500
    else:
        return jsonify(file_load())

# ── Members ───────────────────────────────────────────────────────────────────
@app.route('/api/teams/<team_id>/members', methods=['POST'])
def add_member(team_id):
    payload = request.get_json() or {}
    name = payload.get('name', '').strip()
    if not name:
        return '', 400
    songs = payload.get('songs', None)
    move_from = payload.get('move_from', None)  # member id to remove from old team
    member = {'id': secrets.token_urlsafe(6), 'name': name, 'songs': songs if songs is not None else empty_songs()}
    def patch(data):
        if move_from:
            for t in data['teams']:
                t['members'] = [m for m in t['members'] if m['id'] != move_from]
        for t in data['teams']:
            if t['id'] == team_id:
                t['members'].append(member)
    with_data(patch)
    return jsonify(member), 201

@app.route('/api/members/<member_id>', methods=['PUT'])
def update_member(member_id):
    payload = request.get_json() or {}
    result = {}
    def patch(data):
        for team in data['teams']:
            for i, m in enumerate(team['members']):
                if m['id'] == member_id:
                    team['members'][i] = {**m, 'name': payload.get('name', m['name']), 'songs': payload.get('songs', m['songs'])}
                    result.update(team['members'][i])
    with_data(patch)
    return (jsonify(result), 200) if result else ('', 404)

@app.route('/api/members/<member_id>', methods=['DELETE'])
def delete_member(member_id):
    def patch(data):
        for team in data['teams']:
            team['members'] = [m for m in team['members'] if m['id'] != member_id]
    with_data(patch)
    return '', 204

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3456))
    app.run(host='0.0.0.0', port=port, debug=False)
