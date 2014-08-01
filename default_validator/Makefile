PREFIX=/usr/local/kattis

build: default_validator
clean:
	rm -f default_validator

default_validator: default_validator.cc
	g++ -O3 -o default_validator default_validator.cc
install: default_validator
	mkdir -p $(DESTDIR)$(PREFIX)/bin/
	cp default_validator $(DESTDIR)$(PREFIX)/bin/default_validator
