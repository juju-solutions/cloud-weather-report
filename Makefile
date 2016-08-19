all:
	@echo "Available targets:"
	@echo "  test"
	@echo "  lint"
	@echo "  cover"
	@echo "  clean"
apt_prereqs:
	@for i in $(APT_PREREQS); do dpkg -l | grep -w $$i[^-] >/dev/null || sudo apt-get install -y $$i; done
	@# Need tox, but dont install the apt version unless we have to (dont want to conflict with pip)
	@which tox >/dev/null || sudo apt-get install -y python-tox
test: apt_prereqs
	tox
lint:
	tox -e lint
clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete
	rm -rf .tox
.PHONY: all apt_prereqs test lint clean
