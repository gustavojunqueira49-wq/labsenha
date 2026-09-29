#!/usr/bin/env bash
cd "$(dirname "$0")/../backend" && exec .venv/bin/python -m app.cli run
