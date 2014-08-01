PREFIX=/usr/local/kattis
PROGRAM=interactive

build: $(PROGRAM)
clean:
	rm -f $(PROGRAM)

%: %.cc
	g++ -O3 -o $@ $<

install: $(PROGRAM)
	mkdir -p $(DESTDIR)$(PREFIX)/bin/
	cp $(PROGRAM) $(DESTDIR)$(PREFIX)/bin/$(PROGRAM)
