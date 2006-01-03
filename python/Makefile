# check for signs of Unix
find_init := $(strip $(wildcard /sbin/init) \
	                     $(wildcard /usr/sbin/init) \
	 	                 $(wildcard /hurd/auth))

# include the appropriate sub-makefile
ifeq ($(find_init),)
  include win32.mk
else
  include unix_v5.mk
endif # test is_unix

all: aculab/_lowlevel$(SO) aculab/lowlevel.py # info

aculab/_lowlevel$(SO): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(PYTHON_LIBDIR) $(PYTHON_LIBS) \
		$(ACULAB_LIBDIR) $(ACULAB_LIBS) $(POST_LDFLAGS)

lowlevel_wrap.c aculab/lowlevel.py: lowlevel.i
	$(SWIG) $(DEFINES) -modern -new_repr -python $(ACULAB_INCLUDE) $<
	mv lowlevel.py aculab

%$(O): %.c
	$(CC) -c $(C_DEFINES) $(ACULAB_INCLUDE) $(PYTHON_INCLUDE) $< -o $@ 

install:
	python setup.py install

clean:
	rm -f aculab/*$(SO) *$(O) aculab/*.pyc \
		lowlevel.py *_wrap.c *_wrap.doc $(CRUFT)
	rm -rf build dist
