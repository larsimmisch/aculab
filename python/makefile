# makefile for aculab swig wrapper

CXX		:= cl /MD

DEFINES := -DWIN32

SWIGBIN := c:/swig-1.3.12
SWIGLIB := c:/swig-1.3.12/Lib

PYTHON_INCLUDES = c:/python21/include
PYTHON_LIBS	= c:/python21/libs/python21.lib

OBJS	:= acu_wrap.obj cllib.obj clnt.obj common.obj swlib.obj swnt.obj \
			smnt.obj smbesp.obj smlib.obj smfwcaps.obj

all: aculabc.dll

aculabc.dll: $(OBJS)
	$(CXX) $(LDFLAGS) /LD -o $@ $(OBJS) $(PYTHON_LIBS) \
		 /link /EXPORT:initaculabc

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

%_wrap.c: %.i
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
	rm -f *.dll *.exe *.obj *.lib *.exp *.pyc \
		acu.i *_wrap.c *_wrap.doc
	rm -rf build dist
