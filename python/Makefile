# check for signs of Unix
find_init := $(strip $(wildcard /sbin/init) \
	                     $(wildcard /usr/sbin/init) \
	 	                 $(wildcard /hurd/auth))

# check for signs of Aculab v6
find_v6 := $(strip $(wildcard $(ACULAB_ROOT)/include/cl_lib.h))

# include the appropriate definitions
ifeq ($(find_init),)
  include win32.mk
else
  ifneq ($(find_v6),)
    include unix.mk
  else
    include unix_v5.mk
  endif
endif # test is_unix

all: aculab/_lowlevel$(SO) aculab/lowlevel.py

aculab/_lowlevel$(SO): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(PYTHON_LIBDIR) $(PYTHON_LIBS) \
		$(EXTRA_OBJS) $(ACULAB_LIBDIR) $(ACULAB_LIBS) $(POST_LDFLAGS)

lowlevel_wrap.c aculab/lowlevel.py: lowlevel.i
	$(SWIG) $(DEFINES) -modern -new_repr -python $(ACULAB_INCLUDE) $<
	mv lowlevel.py aculab

%$(O): %.c
	$(CC) -c $(C_DEFINES) $(ACULAB_INCLUDE) $(PYTHON_INCLUDE) $< -o $@ 

ifneq ($(find_v6),)
cl_lib.h2: $(DTK)/include/cl_lib.h cl_lib.patch
	patch -o $@ $(DTK)/include/cl_lib.h cl_lib.patch

res_lib.h2: $(DTK)/include/res_lib.h res_lib.patch
	patch -o $@ $(DTK)/include/res_lib.h res_lib.patch

#actiff.h2: $(DTK)/$(FAX)/include/actiff.h actiff.patch
#	patch -o $@ $(DTK)/$(FAX)/include/actiff.h actiff.patch

bfile.h2: $(DTK)/ting/include/bfile.h bfile.patch
	patch -o $@ $(DTK)/ting/include/bfile.h bfile.patch

# builds are very slow - only rebuild if cl_lib.h changes
sized_struct.i: $(DTK)/include/cl_lib.h $(DTK)/include/sw_lib.h
	swig $(DEFINES) $(DTK_INCLUDE) -xml -xmllite lowlevel.i
	python sized_struct.py lowlevel_wrap.xml
	rm lowlevel_wrap.xml
else
smosintf.h2: $(DTK)/speech/include/smosintf.h smosintf.patch
	patch -o $@ $(DTK)/speech/include/smosintf.h smosintf.patch
endif

install:
	python setup.py install

clean:
	rm -f aculab/*$(SO) *$(O) aculab/*.pyc \
		lowlevel.py *_wrap.c *_wrap.doc $(CRUFT)
	rm -rf build dist
