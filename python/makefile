# makefile for aculab swig wrapper

CXX		:= cl /MD

DEFINES := -DWIN32

SWIGBIN := c:/swig-1.3.15
SWIGLIB := c:/swig-1.3.15/Lib

PYTHON_INCLUDES = c:/python22/include
PYTHON_LIBS	= c:/python22/libs/python22.lib

OBJS	:= acu_wrap.obj cllib.obj clnt.obj common.obj swlib.obj swnt.obj \
			smnt.obj smbesp.obj smlib.obj smfwcaps.obj

all: aculab/_lowlevel.dll aculab/lowlevel.py

aculab/_lowlevel.dll: $(OBJS)
	$(CXX) $(LDFLAGS) /LD -o $@ $(OBJS) $(PYTHON_LIBS) \
		 /link /EXPORT:init_lowlevel

aculab/lowlevel.py: lowlevel.py
	mv lowlevel.py aculab/lowlevel.py

acu.i: top.i ../include/mvcldrvr.h ../include/mvswdrvr.h ../include/smdrvr.h \
	   ../include/smosintf.h makefile
	cat top.i >$@
	cat ../include/mvswdrvr.h >> $@
	cat ../include/mvcldrvr.h >> $@
	cat ../include/smosintf.h >> $@
	cat ../include/smdrvr.h >> $@
	cat ../include/smbesp.h >> $@
	cat ../include/smfwcaps.h >> $@
	# cat bottom.i >>$@

acu_wrap.c lowlevel.py: acu.i
	$(SWIGBIN)/swig $(DEFINES) -I$(SWIGLIB) -I$(SWIGLIB)/Python -I../include \
					-shadow -python $<

%.obj: ../src/%.c
	$(CXX) -c -I$(PYTHON_INCLUDES) -I../include $(DEFINES) $< -o $@ 

%.obj: %.c
	$(CXX) -c -I$(PYTHON_INCLUDES) -I../include $(DEFINES) $< -o $@ 

test:
	python test_swig.py

install:
	python setup.py install

installer:
	python setup.py bdist_wininst

clean:
	rm -f aculab/*.dll *.obj aculab/*.lib aculab/*.exp aculab/*.pyc \
		lowlevel.py acu.i *_wrap.c *_wrap.doc
	rm -rf build dist
