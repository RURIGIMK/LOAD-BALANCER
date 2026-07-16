import os
from flask import Flask, jsonify

app = Flask(__name__)
server_id = os.environ.get('SERVER_ID', 'unknown')  # set by LB via docker -e SERVER_ID=...

@app.route('/home', methods=['GET'])
def home():
    # Identifies which backend served the request, used by LB tests/analysis
    return jsonify({
        "message": f"Hello from Server: {server_id}",
        "status": "successful"
    }), 200

@app.route('/heartbeat', methods=['GET'])
def heartbeat():
    # Polled by LB's health_check loop; any non-200/exception marks server dead
    return '', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)