.PHONY: build run stop clean

build:
	docker build -t server ./server
	docker build -t lb ./lb

run: build
	docker-compose up

stop:
	docker-compose down

clean: stop
	docker rmi server lb || true