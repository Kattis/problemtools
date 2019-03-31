PROGRAM=interactive

build: $(PROGRAM)
clean:
	rm -f $(PROGRAM)

%: %.cc
	g++ -O3 -Wall -o $@ $<
