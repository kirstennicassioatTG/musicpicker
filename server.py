import json
import os
import secrets
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

DATA_FILE = 'data.json'

app = Flask(__name__)
CORS(app)

def backfill_ids(data):
    changed = False
    for team in data.get('teams', []):
        for member in team.get('members', []):
            if 'id' not in member:
                member['id'] = secrets.token_urlsafe(6)
                changed = True
    return changed

def load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            if backfill_ids(data):
                save(data)
            return data
        except Exception:
            pass
    return {'activeTeamId': None, 'teams': []}

def save(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

store = load()

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
    app.run(host='0.0.0.0', port=3456, debug=False)
