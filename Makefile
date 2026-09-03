.PHONY: lint format test ci install reinstall

# Aligné Home Assistant : 3.14 (HA 2026.x) > 3.13 (plancher HA 2025.9).
# Cherche aussi ~/.local/bin (python installé via `uv python install`).
PYTHON_BIN := $(shell \
	command -v python3.14 2>/dev/null \
	|| command -v python3.13 2>/dev/null \
	|| ls $(HOME)/.local/bin/python3.14 2>/dev/null \
	|| ls $(HOME)/.local/bin/python3.13 2>/dev/null \
)

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
RUFF ?= .venv/bin/ruff
PYTEST ?= .venv/bin/pytest

install:
	@if [ -z "$(PYTHON_BIN)" ]; then \
		echo "Erreur: Python 3.13+ requis (aligné Home Assistant 2025.9+)."; \
		echo "Installation recommandée (sans sudo) :"; \
		echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "  export PATH=\"\$$HOME/.local/bin:\$$PATH\""; \
		echo "  uv python install 3.14"; \
		echo "  make reinstall"; \
		echo "Ou via apt (deadsnakes) : python3.14 python3.14-venv"; \
		exit 1; \
	fi
	@echo "Interpréteur: $$($(PYTHON_BIN) --version)"
	@$(PYTHON_BIN) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' \
		|| { echo "Erreur: $$($(PYTHON_BIN) --version) < 3.13"; exit 1; }
	@desired="$$($(PYTHON_BIN) -c 'import sys; print("%d.%d" % sys.version_info[:2])')"; \
	if [ -x .venv/bin/python ]; then \
		current="$$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo none)"; \
		if [ "$$current" != "$$desired" ]; then \
			echo "Recréation du venv ($$current → $$desired)…"; \
			rm -rf .venv; \
		fi; \
	fi
	@$(PYTHON_BIN) -m venv .venv
	@$(PIP) install -q --upgrade pip
	@$(PIP) install -q -r requirements_test.txt
	@echo "OK — $$(.venv/bin/python --version) (HA : 3.14 préféré, 3.13 mini)"

reinstall:
	rm -rf .venv
	$(MAKE) install

lint:
	$(RUFF) check custom_components tests --fix
	$(RUFF) format custom_components tests

format: lint

test:
	$(PYTEST) --cov=custom_components/optifamily --cov-report=term-missing

ci:
	$(RUFF) check custom_components tests
	$(RUFF) format --check custom_components tests
	$(PYTEST) --cov=custom_components/optifamily --cov-report=term-missing
