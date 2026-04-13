import json
import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

DATA_FILE = 'data.json'

app = Flask(__name__)
CORS(app)

def load():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
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
