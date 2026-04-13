from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

store = {"activeTeamId": None, "teams": []}

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
    return '', 204

if __name__ == '__main__':
    app.run(port=3456, debug=False)
