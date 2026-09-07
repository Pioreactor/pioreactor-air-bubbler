PYTHON ?= ../pioreactor/.venv/bin/python

.PHONY: build clean-build

build: clean-build
	$(PYTHON) -m build --wheel --no-isolation

clean-build:
	rm -rf build pioreactor_air_bubbler.egg-info
