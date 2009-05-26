ifeq ($(PYTHON),)

py_versions:=2.6 2.5

$(foreach ver, $(py_versions), )

python2.5 := $(strip $(wildcard /usr/bin/python2.5)
                     $(wildcard /usr/local/bin/python2.5))
python2.6 := $(strip $(wildcard /usr/bin/python2.6)
                     $(wildcard /usr/local/bin/python2.6))
ifneq ($(python2.6),)
PYTHON=python2.6
endif
ifneq ($(python2.6),)
PYTHON=python2.6
endif
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
