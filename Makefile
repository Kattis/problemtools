all:
	make -C support

builddeb:
	dpkg-buildpackage -us -uc -tc -b
