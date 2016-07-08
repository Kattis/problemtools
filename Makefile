PACKAGE=problemtools
LIBDIR=$(DESTDIR)/usr/lib/$(PACKAGE)/
ETCDIR=$(DESTDIR)/etc/kattis/problemtools

all:
	make -C support

builddeb:
	dpkg-buildpackage -us -uc -tc -b

install:
	python setup.py install --root $(DESTDIR)
	install -d $(ETCDIR)
	install etc/* $(ETCDIR)
	install -d $(LIBDIR)
	cp -r examples $(LIBDIR)/

clean:
	make -C support clean
	python setup.py clean --all
	rm -rf dist

distclean: clean
	rm -f $(CONF)
