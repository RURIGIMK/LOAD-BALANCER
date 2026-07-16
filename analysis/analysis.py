import requests  # HTTP client to hit the load balancer's API
import random  # unused directly here but kept for parity with lb-side randomness assumptions
import time  # sleeps between scaling operations and failure-recovery polling
import threading  # run concurrent client workers to simulate async load
import subprocess  # shell out to `docker kill` for the failure-injection test
import matplotlib.pyplot as plt  # plotting bar/line charts for the analysis
from collections import Counter  # tally which server handled each request

LB_URL = "http://localhost:5000"  # load balancer exposed on the host at this port

def send_request():
    try:
        resp = requests.get(f"{LB_URL}/home", timeout=2)  # hit /home, which the LB routes to some replica
        if resp.status_code == 200:
            data = resp.json()  # parse the {"message": "Hello from Server: X", ...} body
            msg = data.get('message', '')
            if 'Server:' in msg:
                return msg.split('Server:')[1].strip()  # extract just the server identifier, e.g. "Server2"
    except:
        return None  # network error, timeout, etc. - count as a dropped request
    return None  # non-200 or missing message field

def run_experiment(total=10000, concurrency=50):
    results = []  # shared list of server IDs that answered each request
    def worker():
        for _ in range(total // concurrency):  # each worker fires its share of the total requests
            sid = send_request()
            if sid:
                results.append(sid)  # list.append is thread-safe under the GIL for this simple case
    threads = []
    for _ in range(concurrency):  # spawn worker threads to approximate concurrent/async clients
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()  # wait for all workers to finish before returning
    return results

def experiment_a1(tag="A1"):
    print(f"{tag}: 10000 requests, N=3")  # progress marker
    results = run_experiment(10000)  # fire 10k requests against whatever N is currently configured
    counter = Counter(results)  # count how many landed on each server
    print("Counts:", counter)
    servers = sorted(counter.keys())  # stable ordering for the chart
    counts = [counter[s] for s in servers]
    plt.figure()  # fresh figure so repeated calls (A1 vs A4_A1) don't overlap
    plt.bar(servers, counts)  # bar chart of per-server request counts
    plt.title(f"Request distribution with N=3 ({tag})")
    plt.xlabel("Server")
    plt.ylabel("Number of requests")
    plt.savefig(f"{tag}_bar.png")  # save the chart for the README/report
    with open(f"{tag}_bar_counts.txt", "w") as f:
        f.write(str(dict(counter)))  # dump raw counts alongside the image
    return dict(counter)

def experiment_a2(tag="A2"):
    print(f"{tag}: Vary N from 2 to 6")  # progress marker
    avg_loads = []  # average requests handled per server at each N
    N_values = list(range(2, 7))  # spec: N from 2 to 6 inclusive
    for N in N_values:
        # Adjust LB to have exactly N servers
        rep = requests.get(f"{LB_URL}/rep").json()  # check current replica count
        current = rep['message']['N']
        if current < N:
            requests.post(f"{LB_URL}/add", json={"n": N - current, "hostnames": []})  # scale up to N
        elif current > N:
            requests.delete(f"{LB_URL}/rm", json={"n": current - N, "hostnames": []})  # scale down to N
        # Wait for changes to take effect
        time.sleep(2)  # give new/removed containers time to become reachable/torn down
        results = run_experiment(10000)  # 10k requests at this N
        total = len(results)
        avg = total / N if N > 0 else 0  # average load per server for this N
        avg_loads.append(avg)
        print(f"N={N}, avg load/server = {avg}")
    plt.figure()  # fresh figure for this chart
    plt.plot(N_values, avg_loads, marker='o')  # line chart of avg load vs N
    plt.title(f"Average load per server vs N ({tag})")
    plt.xlabel("N (number of servers)")
    plt.ylabel("Average requests per server")
    plt.savefig(f"{tag}_line.png")  # save chart
    with open(f"{tag}_line_data.txt", "w") as f:
        f.write(str(list(zip(N_values, avg_loads))))  # dump raw (N, avg) pairs
    return dict(zip(N_values, avg_loads))

def experiment_a3():
    """Test all LB endpoints and demonstrate failure recovery."""
    log = []  # accumulates a human-readable transcript of the test run
    def record(name, resp):
        entry = f"{name}: status={resp.status_code} body={resp.text}"  # capture status + body for evidence
        print(entry)
        log.append(entry)

    record("GET /rep", requests.get(f"{LB_URL}/rep"))  # check replica listing works
    record("POST /add", requests.post(f"{LB_URL}/add", json={"n": 1, "hostnames": ["S_test"]}))  # exercise scale-up
    record("GET /home", requests.get(f"{LB_URL}/home"))  # exercise routed request
    record("GET /unknown", requests.get(f"{LB_URL}/unknown"))  # exercise the 400 unknown-endpoint path
    record("DELETE /rm", requests.delete(f"{LB_URL}/rm", json={"n": 1, "hostnames": ["S_test"]}))  # exercise scale-down, removing the server we just added

    # Failure recovery: kill a server container and observe replacement via /rep.
    rep_before = requests.get(f"{LB_URL}/rep").json()  # snapshot replica set before the failure
    log.append(f"Before kill: {rep_before}")
    victim = rep_before['message']['replicas'][0]  # pick the first replica to kill
    subprocess.run(["docker", "kill", victim])  # simulate a hard crash (SIGKILL) of that container
    log.append(f"Killed container: {victim}")
    for _ in range(15):  # poll up to ~30s for the LB's health check to notice and replace it
        time.sleep(2)
        rep_after = requests.get(f"{LB_URL}/rep").json()
        if victim not in rep_after['message']['replicas']:
            log.append(f"Recovered. New replica set: {rep_after}")  # LB spawned a replacement and dropped the dead one
            break
    else:
        log.append("Replacement did not complete within timeout window.")  # health check interval may need tuning, or LB is stuck

    with open("A3_failure_log.txt", "w") as f:
        f.write("\n".join(log))  # persist the full transcript as evidence for the README
    return log

if __name__ == "__main__":  # CLI entry point, only runs when executed directly
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"  # choose which experiment(s) to run: all, a1, a2, a3, a4
    if mode in ("all", "a1"):
        experiment_a1("A1")  # baseline N=3 distribution
    if mode in ("all", "a2"):
        experiment_a2("A2")  # scalability sweep N=2..6
    if mode in ("all", "a3"):
        experiment_a3()  # endpoint sanity + failure recovery
    if mode == "a4":
        # Run against a LB started with HASH_VARIANT=alt (see Makefile target `run-alt-hash`).
        experiment_a1("A4_A1")  # repeat A-1 with the alternate hash functions
        experiment_a2("A4_A2")  # repeat A-2 with the alternate hash functions
