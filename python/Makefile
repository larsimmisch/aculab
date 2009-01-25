ifeq ($(PYTHON),)
PYTHON=python2.5
endif

all: 
	$(PYTHON) setup.py build_ext -i

install:
	$(PYTHON) setup.py install

clean:
	rm -f aculab/*.pyd aculab/*.pyc \
		lowlevel.py *_wrap.c *_wrap.doc MANIFEST
	rm -rf build dist

wininst_publish:
	$(PYTHON) setup.py bdist_wininst
	scp dist/*.exe borel:/Library/WWW/aculab

distclean: clean
	rm -f *.h2 sized_struct.i aculab/lowlevel.py aculab/_lowlevel.*
