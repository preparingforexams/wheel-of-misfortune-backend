.PHONY: check nice test

check: nice test

nice:
	poetry run black src/
	poetry run mypy src/

test:
	echo "There are no tests you dingus"
	# poetry run pytest src/
