# check for signs of Unix
find_init := $(strip $(wildcard /sbin/init) \
	                 $(wildcard /usr/sbin/init))

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

ifneq ($(find_v6),)
cl_lib.h2: $(DTK)/include/cl_lib.h cl_lib.patch
	patch -o $@ $(DTK)/include/cl_lib.h cl_lib.patch

#res_lib.h2: $(DTK)/include/res_lib.h res_lib.patch
#	patch -o $@ $(DTK)/include/res_lib.h res_lib.patch

#actiff.h2: $(DTK)/$(FAX)/include/actiff.h actiff.patch
#	patch -o $@ $(DTK)/$(FAX)/include/actiff.h actiff.patch

#bfile.h2: $(DTK)/ting/include/bfile.h bfile.patch
#	patch -o $@ $(DTK)/ting/include/bfile.h bfile.patch

# builds are very slow - only rebuild if cl_lib.h changes
# exclude structures that are %extended already
sized_struct.i: $(DTK)/include/cl_lib.h $(DTK)/include/sw_lib.h
	swig $(DEFINES) $(SWIG_DEFINES) $(ACULAB_INCLUDE) -xml -xmllite lowlevel.i
	python sized_struct.py -x ACU_SNAPSHOT_PARMS lowlevel_wrap.xml
	rm lowlevel_wrap.xml

lowlevel_wrap.c aculab/lowlevel.py: lowlevel.i cl_lib.h2 sized_struct.i
	$(SWIG) $(DEFINES) $(SWIG_DEFINES) -O -new_repr -python $(ACULAB_INCLUDE) $<
	mv lowlevel.py aculab

else
smosintf.h2: $(DTK)/speech/include/smosintf.h smosintf.patch
	patch -o $@ $(DTK)/speech/include/smosintf.h smosintf.patch

lowlevel_wrap.c aculab/lowlevel.py: lowlevel.i smosintf.h2
	$(SWIG) $(DEFINES) -modern -new_repr -python $(ACULAB_INCLUDE) $<
	mv lowlevel.py aculab
endif

aculab/_lowlevel$(SO): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS) $(EXTRA_OBJS) $(PYTHON_LIBDIR) \
		$(ACULAB_LIBDIR) $(PYTHON_LIBS) $(ACULAB_LIBS) $(POST_LDFLAGS)

%$(O): %.c
	$(CC) -c $(C_DEFINES) $(ACULAB_INCLUDE) $(PYTHON_INCLUDE) $< -o $@ 

# To generate a patch, (with the example cl_lib.h), copy a the original 
# cl_lib.h to cl_lib.h2, edit it, and then do:
# diff -u $(DTK)/include/cl_lib.h cl_lib.h2 > cl_lib.patch

install:
	python install.py aculab

clean:
	rm -f aculab/*$(SO) *$(O) aculab/*.pyc \
		lowlevel.py *_wrap.c *_wrap.doc MANIFEST $(CRUFT)
	rm -rf build dist
