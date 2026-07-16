# Customizable Load Balancer – Distributed Systems Assignment

## Design Choices
- **Language**: Python (Flask) for simplicity and rapid prototyping.
- **Consistent Hashing**: 512 slots (M), 9 virtual nodes per server (K = log2(512)).
  Default hash functions per spec: `H(i) = i^2 + 2i + 17` (request -> slot),
  `Phi(i,j) = i^2 + j^2 + 2j + 25` (virtual server -> slot). Quadratic probing
  resolves collisions when placing virtual server slots (`lb/consistent_hash.py`).
  Set `HASH_VARIANT=alt` on the lb container to use the modified hash functions
  used for the Task4/A-4 comparison.
- **Container Management**: Uses `docker` CLI via subprocess; the load balancer runs as a privileged container with the Docker socket mounted.
- **Fault Tolerance**: A background thread periodically checks `/heartbeat`; failed servers are replaced with new random-named containers.
- **Scaling**: `/add` and `/rm` endpoints allow dynamic scaling. Provided hostnames are respected; random names are generated for the rest.
- **Unknown endpoints**: `GET /<path>` returns `400` with
  `"<Error> '/<path>' endpoint does not exist in server replicas"` for any path
  not registered on the server (only `/home` and `/heartbeat` are valid).

## Assumptions
- All containers run on the same Docker network `net1`.
- The server image is named `server:latest` (built from `server/`).
- The load balancer itself runs on port 5000 (mapped to host).
- Request IDs are 6‑digit random numbers generated per request.

## Running the System
1. Clone the repository.
2. Run `make build` to build both images.
3. Run `make run` to start the load balancer (and initial 3 servers).
4. Use `make stop` to tear down.
5. Run `python3 analysis/analysis.py all` (host needs `requests` and `matplotlib`)
   to perform A-1, A-2, and A-3 experiments against the running stack.
6. For A-4, stop the stack, run `make run-alt-hash` (starts the lb with the
   modified hash functions), then run `python3 analysis/analysis.py a4`.

## Testing
- Use `curl` or `httpie` to test endpoints:
  - `GET http://localhost:5000/rep`
  - `POST http://localhost:5000/add` with JSON `{"n": 2, "hostnames": ["S5","S6"]}`
  - `DELETE http://localhost:5000/rm` with JSON `{"n": 1, "hostnames": ["Server1"]}`
  - `GET http://localhost:5000/home` – forwarded to a server.
  - `GET http://localhost:5000/unknown` – returns `400` with the
    "endpoint does not exist" error.
- `analysis/analysis.py a3` exercises `/rep`, `/add`, `/home`, an unknown path,
  `/rm`, then kills a server container with `docker kill` and polls `/rep`
  until the load balancer has spawned and registered a replacement,
  logging every step to `A3_failure_log.txt`.

## Performance Analysis
Run `make run` then `python3 analysis/analysis.py all` to regenerate the
figures/data files below before submission — this repo ships the analysis
tooling but the actual experiment artifacts (`A1_bar.png`, `A2_line.png`,
`A3_failure_log.txt`, `A4_*`) must be produced by running the stack in a
Docker-capable environment.

- **A‑1** (`A1_bar.png`, `A1_bar_counts.txt`): 10,000 requests against N=3.
  Expect the three servers to receive close to 3,333 requests each; report the
  actual counts and variance once generated, and note that residual imbalance
  comes from uneven virtual-node spacing on the ring (9 virtual nodes/server
  keeps this small).
- **A‑2** (`A2_line.png`, `A2_line_data.txt`): N stepped from 2 to 6, 10,000
  requests per step. Expect average load per server (10000/N) to fall roughly
  hyperbolically as N grows — report the measured curve and compare to the
  ideal 10000/N line to comment on scalability overhead (container
  start-up time, ring rebalancing).
- **A‑3** (`A3_failure_log.txt`): Exercises every load balancer endpoint and
  records a `docker kill` of one replica plus the polling loop that confirms
  the load balancer detects the failure via `/heartbeat` and spawns/registers
  a replacement, restoring N replicas.
- **A‑4** (`A4_A1_bar.png`, `A4_A2_line.png`): Same A-1/A-2 experiments run
  against the load balancer started with `HASH_VARIANT=alt`
  (`H(i) = i^2 + 4i + 7`, `Phi(i,j) = 2i^2 + j^2 + 6j + 11`). Compare the
  resulting distribution/scalability plots against the default-hash A-1/A-2
  results and report whether the alternate constants produce a more/less even
  spread across the ring.

## Additional Notes
- The health‑check interval is 5 seconds; adjust as needed.
- All containers are cleaned up when stopping the compose stack.