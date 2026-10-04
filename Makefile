# make seed | make dev | make test   (Windows without make: use scripts\*.ps1)
PY ?= backend/.venv/bin/python
ifeq ($(OS),Windows_NT)
PY = backend/.venv/Scripts/python
endif

setup:
	python -m venv backend/.venv && $(PY) -m pip install -r backend/requirements.txt && cd frontend && npm install

seed:
	cd backend && ../$(PY) scripts/seed.py

dev:
	cd backend && ../$(PY) -m uvicorn app.main:app --port 8000 --reload & cd frontend && npm run dev

test:
	cd backend && ../$(PY) -m pytest -q
