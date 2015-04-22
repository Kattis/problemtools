PROGRAM=default_validator

build: $(PROGRAM)
clean:
	rm -f $(PROGRAM)

%: %.cc
	g++ -O3 -o $@ $<
