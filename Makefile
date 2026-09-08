.PHONY: test validate

test:
	python3 -m unittest discover -s tests -p "test_*.py"

validate: test
	./scripts/validate-skills.sh
