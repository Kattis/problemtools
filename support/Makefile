PACKAGE=problemtools
CONF=checktestdata/config.mk
PROGRAMS=checktestdata default_validator interactive

all: $(CONF)
	$(foreach prog,$(PROGRAMS),$(MAKE) -C $(prog);)

install: all
	install -d $(DESTDIR)
	$(foreach prog,$(PROGRAMS),install $(prog)/$(prog) $(DESTDIR);)
	install default_grader/default_grader $(DESTDIR)
	cp viva/viva.jar $(DESTDIR)
	install viva/viva.sh $(DESTDIR)

$(CONF): checktestdata/bootstrap
	cd checktestdata && ./bootstrap

checktestdata/bootstrap:
	git submodule update --init

clean:
	$(foreach prog,$(PROGRAMS),$(MAKE) -C $(prog) clean;)

distclean: clean
	rm -f $(CONF)
