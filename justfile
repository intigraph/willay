# Willay — mirrored quality/build/docs entry points, with Python commands.
default:
    @just --list

setup:
    uv sync --locked

build:
    uv build --wheel

test *args="":
    uv run --locked pytest {{args}}

lint:
    uv run --locked ruff check src tests
    uv run --locked ty check src

fmt:
    uv run --locked ruff format src tests

check:
    uv run --locked ruff format --check src tests
    just lint
    just test "-q"

run *args="":
    uv run --locked willay {{args}}

docs:
    mdbook build docs/book

install:
    uv tool install --from . willay
