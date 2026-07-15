# Customizable Load Balancer – Distributed Systems Assignment

## Design Choices
- **Language**: Python (Flask) for simplicity and rapid prototyping.
- **Consistent Hashing**: Implemented with 512 slots, 9 virtual nodes per server. Linear probing resolves collisions.
- **Container Management**: Uses Docker SDK via subprocess; the load balancer runs as a privileged container with the Docker socket mounted.
- **Fault Tolerance**: A background thread periodically checks `/heartbeat`; failed servers are replaced with new random-named containers.
- **Scaling**: `/add` and `/rm` endpoints allow dynamic scaling. Provided hostnames are respected; random names are generated for the rest.

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
5. Run `analysis/analysis.py` (host needs `requests` and `matplotlib`) to perform experiments.

## Testing
- Use `curl` or `httpie` to test endpoints:
  - `GET http://localhost:5000/rep`
  - `POST http://localhost:5000/add` with JSON `{"n": 2, "hostnames": ["S5","S6"]}`
  - `DELETE http://localhost:5000/rm` with JSON `{"n": 1, "hostnames": ["Server1"]}`
  - `GET http://localhost:5000/home` – forwarded to a server.

## Performance Analysis
- **A‑1**: With N=3, 10k requests are fairly evenly distributed (minor variance due to hashing).
- **A‑2**: Increasing N reduces average load per server, showing scalability.
- **A‑3**: Killing a server container triggers replacement within the health‑check interval; the new container is added to the hash ring and starts serving requests.
- **A‑4**: Changing the hash functions (e.g., using different multipliers) affects distribution; the original functions gave a balanced spread. The experiments were repeated with modified functions and the results are discussed in the full report.

## Additional Notes
- The health‑check interval is 5 seconds; adjust as needed.
- All containers are cleaned up when stopping the compose stack.