import os  # read SERVER_ID env var set by the load balancer when it spawns this container
from flask import Flask, jsonify  # Flask for HTTP server, jsonify for JSON responses

app = Flask(__name__)  # create the Flask app instance
server_id = os.environ.get('SERVER_ID', 'unknown')  # this replica's identity, injected via -e SERVER_ID=... at docker run

@app.route('/home', methods=['GET'])  # register GET /home per Task1 spec
def home():
    return jsonify({  # build the required JSON body
        "message": f"Hello from Server: {server_id}",  # identifies which replica served the request
        "status": "successful"
    }), 200  # explicit 200 OK

@app.route('/heartbeat', methods=['GET'])  # register GET /heartbeat, polled by the load balancer's health check
def heartbeat():
    return '', 200  # empty body, 200 means alive

if __name__ == '__main__':  # only run the dev server when executed directly (not on import)
    app.run(host='0.0.0.0', port=5000)  # bind all interfaces on port 5000 so other containers can reach it
