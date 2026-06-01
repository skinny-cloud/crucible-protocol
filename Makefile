.PHONY: demo install test audit-bad audit-good clean

demo:
	./demo.sh

install:
	pip install -e .

test:
	pip install -e . && pip install pytest && python -m pytest -q

audit-bad:
	crucible audit examples/known-bad

audit-good:
	crucible audit examples/known-good

clean:
	rm -rf .demo-venv build dist src/*.egg-info **/__pycache__ .pytest_cache
