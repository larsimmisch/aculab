all: 
	python setup.py build_ext -i

install:
	python setup.py install

clean:
	rm -f aculab/*.pyd aculab/*.pyc \
		lowlevel.py *_wrap.c *_wrap.doc MANIFEST
	rm -rf build dist

wininst_publish:
	python setup.py bdist_wininst
	scp dist/*.exe borel:/Library/WWW/aculab

distclean: clean
	rm -f *.h2 sized_struct.i
