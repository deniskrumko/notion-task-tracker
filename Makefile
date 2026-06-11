UV_RUN := uv run --no-editable --dev

.PHONY: fmt lint tests clean-build-artifacts check

fmt:
	@echo "🔧  Formatting..."
	@$(UV_RUN) ruff format .
	@$(UV_RUN) ruff check --fix .

lint:
	@echo "🔧  Linting..."
	@$(UV_RUN) ruff format --check . || (echo "Run make fmt" && exit 1)
	@$(UV_RUN) ruff check .
	@$(UV_RUN) ty check .

tests:
	@echo "🔧  Testing..."
	@$(UV_RUN) pytest

clean-build-artifacts:
	@rm -rf build src/*.egg-info

check: fmt lint tests clean-build-artifacts

deps:
	uv sync --dev
