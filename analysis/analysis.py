import requests
import random
import time
import threading
import matplotlib.pyplot as plt
from collections import Counter

LB_URL = "http://localhost:5000"

def send_request():
    # Hit LB /home once, return which backend server id answered (or None on failure)
    try:
        resp = requests.get(f"{LB_URL}/home", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get('message', '')
            if 'Server:' in msg:
                return msg.split('Server:')[1].strip()
    except:
        return None
    return None

def run_experiment(total=10000, concurrency=50):
    # Fire `total` requests split across `concurrency` worker threads, collect server ids hit
    results = []
    def worker():
        for _ in range(total // concurrency):
            sid = send_request()
            if sid:
                results.append(sid)  # list.append is thread-safe under GIL, no lock needed
    threads = []
    for _ in range(concurrency):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return results

def experiment_a1():
    # A-1: with fixed N=3 servers, check how evenly 10000 requests distribute
    print("A‑1: 10000 requests, N=3")
    results = run_experiment(10000)
    counter = Counter(results)
    print("Counts:", counter)
    servers = sorted(counter.keys())
    counts = [counter[s] for s in servers]
    plt.bar(servers, counts)
    plt.title("Request distribution with N=3")
    plt.xlabel("Server")
    plt.ylabel("Number of requests")
    plt.savefig("A1_bar.png")
    plt.show()

def experiment_a2():
    # A-2: scale LB from N=2 to N=6 servers, measure average load per server at each N
    print("A‑2: Vary N from 2 to 6")
    avg_loads = []
    N_values = list(range(2, 7))
    for N in N_values:
        # Adjust LB to have exactly N servers
        rep = requests.get(f"{LB_URL}/rep").json()
        current = rep['message']['N']
        if current < N:
            requests.post(f"{LB_URL}/add", json={"n": N - current, "hostnames": []})
        elif current > N:
            requests.delete(f"{LB_URL}/rm", json={"n": current - N, "hostnames": []})
        # Wait for changes to take effect
        time.sleep(2)
        results = run_experiment(10000)
        total = len(results)
        avg = total / N if N > 0 else 0
        avg_loads.append(avg)
        print(f"N={N}, avg load/server = {avg}")
    plt.plot(N_values, avg_loads, marker='o')
    plt.title("Average load per server vs N")
    plt.xlabel("N (number of servers)")
    plt.ylabel("Average requests per server")
    plt.savefig("A2_line.png")
    plt.show()

if __name__ == "__main__":
    experiment_a1()
    experiment_a2()