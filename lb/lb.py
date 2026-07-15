import os
import json
import random
import time
import threading
import subprocess
import requests
from flask import Flask, request, jsonify
from consistent_hash import ConsistentHash

app = Flask(__name__)

# Constants
M = 512
K = 9
NETWORK = "net1"
SERVER_IMAGE = os.environ.get('SERVER_IMAGE', 'server:latest')
INITIAL_N = 3
HEALTH_CHECK_INTERVAL = 5

# Global state
active_servers = []          # list of container names (hostnames)
ch = ConsistentHash(M=M, K=K)
lock = threading.Lock()

def generate_random_name():
    return "S" + ''.join(random.choices('0123456789', k=6))

def start_container(name):
    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--network", NETWORK,
        "--network-alias", name,
        "-e", f"SERVER_ID={name}",
        SERVER_IMAGE
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to start container {name}: {e.stderr}")
        return False

def stop_container(name):
    try:
        subprocess.run(["docker", "stop", name], check=True)
        subprocess.run(["docker", "rm", name], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop/remove {name}: {e.stderr}")
        return False

def initialize_servers():
    global active_servers
    with lock:
        for i in range(1, INITIAL_N + 1):
            name = f"Server{i}"
            if start_container(name):
                active_servers.append(name)
                ch.add_server(name)
            else:
                print(f"Failed to start initial server {name}")

def health_check():
    while True:
        time.sleep(HEALTH_CHECK_INTERVAL)
        with lock:
            to_check = active_servers.copy()
        for server in to_check:
            try:
                resp = requests.get(f"http://{server}:5000/heartbeat", timeout=2)
                if resp.status_code != 200:
                    raise Exception("Non-200")
            except:
                print(f"Server {server} failed health check. Replacing...")
                with lock:
                    if server not in active_servers:
                        continue
                    ch.remove_server(server)
                    active_servers.remove(server)
                    stop_container(server)
                    new_name = generate_random_name()
                    while new_name in active_servers:
                        new_name = generate_random_name()
                    if start_container(new_name):
                        active_servers.append(new_name)
                        ch.add_server(new_name)
                        print(f"Replaced {server} with {new_name}")
                    else:
                        print(f"Failed to start replacement for {server}")

@app.route('/rep', methods=['GET'])
def get_replicas():
    with lock:
        return jsonify({
            "message": {
                "N": len(active_servers),
                "replicas": active_servers
            },
            "status": "successful"
        }), 200

@app.route('/add', methods=['POST'])
def add_servers():
    data = request.get_json()
    if not data or 'n' not in data:
        return jsonify({"message": "Invalid JSON", "status": "failure"}), 400
    n = data['n']
    if not isinstance(n, int) or n <= 0:
        return jsonify({"message": "n must be positive", "status": "failure"}), 400
    hostnames = data.get('hostnames', [])
    if not isinstance(hostnames, list):
        return jsonify({"message": "hostnames must be a list", "status": "failure"}), 400
    if len(hostnames) > n:
        return jsonify({"message": "Length of hostname list is more than newly added instances", "status": "failure"}), 400

    with lock:
        existing = set(active_servers)
        # Validate provided hostnames
        for name in hostnames:
            if name in existing:
                return jsonify({"message": f"Hostname {name} already active", "status": "failure"}), 400
        # Generate remaining names
        new_names = hostnames.copy()
        for _ in range(n - len(hostnames)):
            new_name = generate_random_name()
            while new_name in existing or new_name in new_names:
                new_name = generate_random_name()
            new_names.append(new_name)
        # Start containers and update state
        for name in new_names:
            if start_container(name):
                active_servers.append(name)
                ch.add_server(name)
            else:
                print(f"Failed to start {name}")
        return jsonify({
            "message": {
                "N": len(active_servers),
                "replicas": active_servers
            },
            "status": "successful"
        }), 200

@app.route('/rm', methods=['DELETE'])
def remove_servers():
    data = request.get_json()
    if not data or 'n' not in data:
        return jsonify({"message": "Invalid JSON", "status": "failure"}), 400
    n = data['n']
    if not isinstance(n, int) or n <= 0:
        return jsonify({"message": "n must be positive", "status": "failure"}), 400
    hostnames = data.get('hostnames', [])
    if not isinstance(hostnames, list):
        return jsonify({"message": "hostnames must be a list", "status": "failure"}), 400
    if len(hostnames) > n:
        return jsonify({"message": "Length of hostname list is more than removable instances", "status": "failure"}), 400

    with lock:
        if len(active_servers) < n:
            return jsonify({"message": "Not enough active servers", "status": "failure"}), 400

        to_remove = set()
        # Add specified hostnames
        for name in hostnames:
            if name in active_servers:
                to_remove.add(name)
            else:
                return jsonify({"message": f"Hostname {name} not active", "status": "failure"}), 400

        # Randomly select more if needed
        remaining = [s for s in active_servers if s not in to_remove]
        while len(to_remove) < n and remaining:
            choice = random.choice(remaining)
            to_remove.add(choice)
            remaining.remove(choice)

        # Remove them
        for name in to_remove:
            ch.remove_server(name)
            active_servers.remove(name)
            stop_container(name)

        return jsonify({
            "message": {
                "N": len(active_servers),
                "replicas": active_servers
            },
            "status": "successful"
        }), 200

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET'])
def forward(path):
    # Avoid interfering with special endpoints
    if path in ['rep', 'add', 'rm']:
        return jsonify({"message": "Not found", "status": "failure"}), 404

    request_id = random.randint(100000, 999999)
    with lock:
        server = ch.get_server(request_id)
        if server is None:
            return jsonify({"message": "No server available", "status": "failure"}), 503

    target_url = f"http://{server}:5000/{path}"
    try:
        resp = requests.get(target_url, params=request.args, timeout=5)
        try:
            return jsonify(resp.json()), resp.status_code
        except:
            return resp.text, resp.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"message": f"Error forwarding: {str(e)}", "status": "failure"}), 500

if __name__ == '__main__':
    initialize_servers()
    health_thread = threading.Thread(target=health_check, daemon=True)
    health_thread.start()
    app.run(host='0.0.0.0', port=5000, threaded=True)