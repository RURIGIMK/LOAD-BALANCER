import os  # read env vars (SERVER_IMAGE, HASH_VARIANT)
import json  # unused directly but kept for JSON-adjacent debugging if needed
import random  # random name generation, random request IDs, random removal choice
import time  # sleep intervals for health checks
import threading  # background health-check thread + lock around shared state
import subprocess  # shell out to the docker CLI to spawn/kill containers
import requests  # forward client requests to backend servers, poll /heartbeat
from flask import Flask, request, jsonify  # HTTP server framework
from consistent_hash import ConsistentHash  # our Task2 data structure

app = Flask(__name__)  # the load balancer's Flask app

# Constants
M = 512  # number of slots on the consistent hash ring (spec)
K = 9  # virtual nodes per server (spec: log2(512))
NETWORK = "net1"  # docker network all containers join, so they can resolve each other by hostname
SERVER_IMAGE = os.environ.get('SERVER_IMAGE', 'server:latest')  # image used to spawn new server replicas
INITIAL_N = 3  # number of server replicas to boot at startup (spec default N=3)
HEALTH_CHECK_INTERVAL = 5  # seconds between heartbeat polls
# Set HASH_VARIANT=alt to use the modified hash functions for A-4 analysis.
HASH_VARIANT = os.environ.get('HASH_VARIANT', 'default')  # picks default spec formulas or the A-4 comparison formulas

# Global state
active_servers = []          # list of container names (hostnames) currently serving traffic
if HASH_VARIANT == 'alt':
    # Modified hash functions used for Task4 A-4 (different constants).
    ch = ConsistentHash(
        M=M, K=K,
        H=lambda i: (i**2 + 4 * i + 7) % M,  # alternate request hash for A-4 comparison
        Phi=lambda i, j: (2 * i**2 + j**2 + 6 * j + 11) % M,  # alternate virtual-server hash for A-4 comparison
    )
else:
    ch = ConsistentHash(M=M, K=K)  # spec-default hash functions (baked into ConsistentHash)
lock = threading.Lock()  # guards active_servers and ch since health-check thread and Flask handlers both touch them

def generate_random_name():
    return "S" + ''.join(random.choices('0123456789', k=6))  # e.g. "S483920", used when no hostname is supplied

def start_container(name):
    cmd = [
        "docker", "run", "-d",  # detached container
        "--name", name,  # container name == hostname within the docker network
        "--network", NETWORK,  # attach to the shared network so the LB can reach it by name
        "--network-alias", name,  # DNS alias, redundant with --name but explicit
        "-e", f"SERVER_ID={name}",  # tells the server container its own identity for /home responses
        SERVER_IMAGE  # image to run
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)  # run docker CLI, raise on non-zero exit
        return True  # container started successfully
    except subprocess.CalledProcessError as e:
        print(f"Failed to start container {name}: {e.stderr}")  # log docker's stderr for debugging
        return False  # signal failure to caller

def stop_container(name):
    try:
        subprocess.run(["docker", "stop", name], check=True)  # stop the running container
        subprocess.run(["docker", "rm", name], check=True)  # remove it so the name can be reused
        return True  # cleanup succeeded
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop/remove {name}: {e.stderr}")  # log failure reason
        return False  # signal failure to caller

def initialize_servers():
    global active_servers  # we mutate the module-level list
    with lock:  # avoid racing with health_check thread before it even starts
        for i in range(1, INITIAL_N + 1):  # spin up INITIAL_N replicas named Server1..ServerN
            name = f"Server{i}"
            if start_container(name):
                active_servers.append(name)  # track it as active
                ch.add_server(name)  # place its virtual nodes on the ring
            else:
                print(f"Failed to start initial server {name}")  # non-fatal, just log

def health_check():
    while True:  # runs forever in a background daemon thread
        time.sleep(HEALTH_CHECK_INTERVAL)  # poll on a fixed interval
        with lock:
            to_check = active_servers.copy()  # snapshot to avoid holding the lock during network calls
        for server in to_check:
            try:
                resp = requests.get(f"http://{server}:5000/heartbeat", timeout=2)  # ping the replica's heartbeat endpoint
                if resp.status_code != 200:
                    raise Exception("Non-200")  # treat any non-200 as a failure
            except:
                print(f"Server {server} failed health check. Replacing...")  # log the detected failure
                with lock:
                    if server not in active_servers:
                        continue  # already handled (e.g. removed via /rm) between snapshot and now
                    ch.remove_server(server)  # take it off the hash ring immediately
                    active_servers.remove(server)  # drop from the active list
                    stop_container(server)  # clean up the dead/unreachable container
                    new_name = generate_random_name()  # pick a replacement hostname
                    while new_name in active_servers:
                        new_name = generate_random_name()  # avoid name collision with existing replicas
                    if start_container(new_name):
                        active_servers.append(new_name)  # register the replacement
                        ch.add_server(new_name)  # place it on the ring
                        print(f"Replaced {server} with {new_name}")  # confirm recovery
                    else:
                        print(f"Failed to start replacement for {server}")  # replacement attempt failed, will retry next cycle only if re-triggered

@app.route('/rep', methods=['GET'])  # Task3: report current replica set
def get_replicas():
    with lock:  # snapshot active_servers consistently
        return jsonify({
            "message": {
                "N": len(active_servers),  # current replica count
                "replicas": active_servers  # their hostnames
            },
            "status": "successful"
        }), 200

@app.route('/add', methods=['POST'])  # Task3: scale up
def add_servers():
    data = request.get_json()  # parse JSON payload
    if not data or 'n' not in data:
        return jsonify({"message": "Invalid JSON", "status": "failure"}), 400  # payload must at least contain 'n'
    n = data['n']  # number of instances to add
    if not isinstance(n, int) or n <= 0:
        return jsonify({"message": "n must be positive", "status": "failure"}), 400  # sanity check on n
    hostnames = data.get('hostnames', [])  # optional preferred hostnames
    if not isinstance(hostnames, list):
        return jsonify({"message": "hostnames must be a list", "status": "failure"}), 400  # type check
    if len(hostnames) > n:
        return jsonify({"message": "<Error> Length of hostname list is more than newly added instances", "status": "failure"}), 400  # spec-required validation + exact error text

    with lock:
        existing = set(active_servers)  # for O(1) membership checks
        # Validate provided hostnames
        for name in hostnames:
            if name in existing:
                return jsonify({"message": f"Hostname {name} already active", "status": "failure"}), 400  # reject duplicate names
        # Generate remaining names
        new_names = hostnames.copy()  # start with the caller's preferred names
        for _ in range(n - len(hostnames)):  # fill the rest randomly up to n total
            new_name = generate_random_name()
            while new_name in existing or new_name in new_names:
                new_name = generate_random_name()  # avoid collisions with existing or just-generated names
            new_names.append(new_name)
        # Start containers and update state
        for name in new_names:
            if start_container(name):
                active_servers.append(name)  # register as active
                ch.add_server(name)  # place on the ring
            else:
                print(f"Failed to start {name}")  # log but continue with the rest
        return jsonify({
            "message": {
                "N": len(active_servers),  # updated total
                "replicas": active_servers  # updated list
            },
            "status": "successful"
        }), 200

@app.route('/rm', methods=['DELETE'])  # Task3: scale down
def remove_servers():
    data = request.get_json()  # parse JSON payload
    if not data or 'n' not in data:
        return jsonify({"message": "Invalid JSON", "status": "failure"}), 400  # 'n' required
    n = data['n']  # number of instances to remove
    if not isinstance(n, int) or n <= 0:
        return jsonify({"message": "n must be positive", "status": "failure"}), 400  # sanity check
    hostnames = data.get('hostnames', [])  # optional preferred hostnames to remove
    if not isinstance(hostnames, list):
        return jsonify({"message": "hostnames must be a list", "status": "failure"}), 400  # type check
    if len(hostnames) > n:
        return jsonify({"message": "<Error> Length of hostname list is more than removable instances", "status": "failure"}), 400  # spec-required validation + exact error text

    with lock:
        if len(active_servers) < n:
            return jsonify({"message": "Not enough active servers", "status": "failure"}), 400  # can't remove more than exist

        to_remove = set()  # accumulates hostnames slated for removal
        # Add specified hostnames
        for name in hostnames:
            if name in active_servers:
                to_remove.add(name)  # honor caller's explicit choice
            else:
                return jsonify({"message": f"Hostname {name} not active", "status": "failure"}), 400  # can't remove a server that isn't active

        # Randomly select more if needed
        remaining = [s for s in active_servers if s not in to_remove]  # candidates not already chosen
        while len(to_remove) < n and remaining:
            choice = random.choice(remaining)  # pick a random extra server to hit the requested count n
            to_remove.add(choice)
            remaining.remove(choice)

        # Remove them
        for name in to_remove:
            ch.remove_server(name)  # take off the ring first so no new requests route there
            active_servers.remove(name)  # drop from active list
            stop_container(name)  # stop and delete the actual container

        return jsonify({
            "message": {
                "N": len(active_servers),  # updated total
                "replicas": active_servers  # updated list
            },
            "status": "successful"
        }), 200

# Endpoints known to be registered on the server replicas (Task1).
VALID_SERVER_ENDPOINTS = {'home', 'heartbeat'}  # only these paths actually exist on backend servers

@app.route('/', defaults={'path': ''})  # catch bare "/" too
@app.route('/<path:path>', methods=['GET'])  # Task3: generic request routing via consistent hashing
def forward(path):
    # Avoid interfering with special endpoints
    if path in ['rep', 'add', 'rm']:
        return jsonify({"message": "Not found", "status": "failure"}), 404  # these are handled by their own routes above; reaching here would be a routing bug, so 404 defensively

    if path not in VALID_SERVER_ENDPOINTS:
        return jsonify({
            "message": f"<Error> '/{path}' endpoint does not exist in server replicas",  # exact spec error text
            "status": "failure"
        }), 400  # spec requires 400 for unregistered endpoints

    request_id = random.randint(100000, 999999)  # simulate a 6-digit client request ID per spec
    with lock:
        server = ch.get_server(request_id)  # consistent-hash lookup for which replica handles this request
        if server is None:
            return jsonify({"message": "No server available", "status": "failure"}), 503  # no replicas registered at all

    target_url = f"http://{server}:5000/{path}"  # backend reachable by container hostname on the shared network
    try:
        resp = requests.get(target_url, params=request.args, timeout=5)  # forward the GET, preserving query params
        try:
            return jsonify(resp.json()), resp.status_code  # pass through JSON body and status
        except:
            return resp.text, resp.status_code  # backend didn't return JSON, pass through raw text
    except requests.exceptions.RequestException as e:
        return jsonify({"message": f"Error forwarding: {str(e)}", "status": "failure"}), 500  # backend unreachable/errored

if __name__ == '__main__':  # only run when executed directly, not on import
    initialize_servers()  # boot INITIAL_N replicas before accepting traffic
    health_thread = threading.Thread(target=health_check, daemon=True)  # daemon so it dies with the main process
    health_thread.start()  # begin background heartbeat polling
    app.run(host='0.0.0.0', port=5000, threaded=True)  # serve on all interfaces, threaded to handle concurrent requests
