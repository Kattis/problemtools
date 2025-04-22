all: checktestdata
	make -C support

builddeb: checktestdata
	dpkg-buildpackage -us -uc -tc -b

checktestdata: support/checktestdata/bootstrap

support/checktestdata/bootstrap:
	git submodule update --init

clean:
	make -C support clean
	rm -rf problemtools.egg-info build
