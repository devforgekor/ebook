.PHONY: install run-telegrambot run-notifier run-lean-worker test clean

install:
	.venv/bin/python -m pip install -r requirements.txt

run-telegrambot:
	.venv/bin/python -m apps.telegrambot.run_bot

run-notifier:
	.venv/bin/python -m apps.notifier.api.main

run-lean-worker:
	.venv/bin/python -m apps.lean.workers.redis_worker

test:
	.venv/bin/python -m pytest apps/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
