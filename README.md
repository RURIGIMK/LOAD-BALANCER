# Customizable Load Balancer

A containerized distributed systems project that implements a customizable HTTP load balancer with consistent hashing, dynamic scaling, health monitoring, failure recovery, and performance analysis.

## Why this project matters

This project demonstrates more than routing requests. It models the operational concerns that appear in distributed systems: distributing traffic, keeping replicas available, scaling the system, detecting failures, and measuring the effect of design decisions.

## Architecture

```text
                         Client
                           |
                           v
                  +------------------+
                  |  Flask Load      |
                  |    Balancer      |
                  +--------+---------+
                           |
                    Consistent Hash Ring
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
     +---------+      +---------+      +---------+
     | Server  |      | Server  |      | Server  |
     | Replica |      | Replica |      | Replica |
     +---------+      +---------+      +---------+
          ^                ^                ^
          +----------------+----------------+
                           |
                     Health Checks
                           |
                    Failure Recovery
```

## Key capabilities

- Consistent hashing with virtual nodes
- Quadratic probing for virtual node placement
- Docker based server replicas
- Dynamic replica creation and removal
- Periodic health checks through `/heartbeat`
- Automatic replacement of failed server containers
- Request forwarding to healthy replicas
- Explicit handling of unknown endpoints
- Alternate hash configuration for comparative experiments
- Automated performance analysis and experiment tooling

## Technical design

The implementation uses Python and Flask for the load balancer and Docker for isolated service replicas. The default configuration uses 512 hash slots and 9 virtual nodes per server. Requests are mapped to the hash ring and routed to the corresponding replica.

A background health check monitors replicas through `/heartbeat`. When a replica fails, the load balancer detects the failure and creates a replacement container, restoring the expected number of active servers.

The system also exposes `/add` and `/rm` operations for controlled scaling. Hostnames can be supplied explicitly or generated automatically.

## Project structure

```text
.
├── lb/                 # Load balancer implementation and hashing logic
├── server/             # Replica server implementation and Docker setup
├── analysis/           # Performance experiments and analysis scripts
├── docker-compose.yml  # Local distributed deployment
├── Makefile            # Build, run, stop, and experiment commands
└── README.md
```

## Running locally

### Prerequisites

- Docker and Docker Compose
- Python 3
- `requests` and `matplotlib` for analysis

### Start the distributed system

```bash
make build
make run
```

Stop the stack with:

```bash
make stop
```

### Exercise the API

```bash
curl http://localhost:5000/rep
curl http://localhost:5000/home
```

Add replicas:

```bash
curl -X POST http://localhost:5000/add \
  -H "Content-Type: application/json" \
  -d '{"n":2,"hostnames":["S5","S6"]}'
```

Remove replicas:

```bash
curl -X DELETE http://localhost:5000/rm \
  -H "Content-Type: application/json" \
  -d '{"n":1,"hostnames":["Server1"]}'
```

## Performance experiments

The repository includes tooling for four experiments:

- **A1:** request distribution across three replicas
- **A2:** scalability as the number of replicas changes
- **A3:** endpoint behavior and failure recovery after a replica is killed
- **A4:** comparison of the default and alternate hashing functions

Run the standard experiments with:

```bash
python3 analysis/analysis.py all
```

The alternate hash experiment can be run using the repository's `make run-alt-hash` target before executing the A4 analysis.

## Engineering takeaways

The project provided practical experience with distributed request routing, consistent hashing, container orchestration, service health monitoring, failure recovery, dynamic scaling, and experimental evaluation. It also highlights an important systems engineering principle: an implementation should be evaluated not only by whether requests succeed, but by how the system behaves under scale and failure.

## Team

Developed as a distributed systems assignment by Rurigi Maina and project collaborators.
