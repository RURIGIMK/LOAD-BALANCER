.PHONY: build run run-alt-hash stop clean analysis

build:
	docker build -t server ./server
	docker build -t lb ./lb

run: build
	docker-compose up

# A-4: run with modified H/Phi hash functions for comparison.
run-alt-hash: build
	HASH_VARIANT=alt docker-compose up

stop:
	docker-compose down

clean: stop
	docker rmi server lb || true

analysis:
	python3 analysis/analysis.py all