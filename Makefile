CONF=checktestdata/paths.mk
PROGRAMS=checktestdata default_validator interactive

all: $(CONF)
	$(foreach prog,$(PROGRAMS),$(MAKE) -C $(prog);)

checktestdata/paths.mk:
	cd checktestdata && ./bootstrap

clean:
	$(foreach prog,$(PROGRAMS),$(MAKE) -C $(prog) clean;)

