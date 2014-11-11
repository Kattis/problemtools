TARGETS=checktestdata
PREFIX=/usr/local/kattis

build: $(TARGETS)

checktestdata: checktestdata.cc lex.cc libchecktestdata.cc libchecktestdata.h parse.cc parser.h parser.ih parserbase.h parsetype.cc parsetype.h scanner.h scanner.ih scannerbase.h
	g++ -g -O2 -Wall -fstack-protector -fPIE -D_FORTIFY_SOURCE=2 -std=c++11 -o checktestdata checktestdata.cc libchecktestdata.cc parse.cc lex.cc parsetype.cc -fPIE -Wl,-z,relro -Wl,-z,now -lgmpxx -lgmp -lboost_regex

clean:
	rm -f $(TARGETS)

install: build
	mkdir -p $(DESTDIR)$(PREFIX)/bin/
	cp $(TARGETS) $(DESTDIR)$(PREFIX)/bin/
