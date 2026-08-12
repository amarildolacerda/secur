PYTHON=python
PIP=$(PYTHON) -m pip

.PHONY: install run test docker-build docker-up docker-down

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m pytest tests

check: docker-build test

all: check

docker-build:
	docker build -t secur-app .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
