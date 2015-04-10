CONF=support/checktestdata/paths.mk
PROGRAMS=checktestdata default_validator interactive
LIBDIR=$(DESTDIR)/usr/lib/problemtools/
BINDIR=$(DESTDIR)/usr/bin

all: $(CONF)
	$(foreach prog,$(PROGRAMS),$(MAKE) -C support/$(prog);)

builddeb:
	dpkg-buildpackage -us -uc -tc -b

dist:
	make clean
	mkdir -p dist/problemtools
	cp -r src/* dist/problemtools
	cp -r support/* dist/problemtools
	cp -r templates dist/problemtools
	cd dist && tar cvzf ../problemtools-dist.tar.gz problemtools
	rm -rf dist

install: all
	python setup.py install --root $(DESTDIR)
	install -d $(BINDIR)
	install bin/* $(BINDIR)
	install -d $(LIBDIR)/bin
	$(foreach prog,$(PROGRAMS),install support/$(prog)/$(prog) $(LIBDIR)/bin;)
	install support/default_grader/default_grader $(LIBDIR)/bin
	cp support/viva/viva.jar $(LIBDIR)/bin
	install support/viva/viva.sh $(LIBDIR)/bin
	cp -r templates $(LIBDIR)/

$(CONF):
	cd support/checktestdata && ./bootstrap

clean:
	$(foreach prog,$(PROGRAMS),$(MAKE) -C support/$(prog) clean;)
	python setup.py clean --all
	rm -f $(CONF)
	rm -rf dist
