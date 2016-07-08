PACKAGE=problemtools
LIBDIR=$(DESTDIR)/usr/lib/$(PACKAGE)/

all:
	make -C support

builddeb:
	dpkg-buildpackage -us -uc -tc -b

install:
	python setup.py install --root $(DESTDIR)
	install -d $(LIBDIR)
	cp -r examples $(LIBDIR)/

clean:
	make -C support clean
	python setup.py clean --all
	rm -rf dist

distclean: clean
	rm -f $(CONF)
