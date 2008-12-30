#O := .obj
O := .o
SO := .pyd
EXP := .exp
CRUFT := *.opt *.plg *.ncb

# Need to convert to a cygwin path, otherwise the ':' in DTK will upset make
DTK := $(shell cygpath -u "$(ACULAB_ROOT)")

# And swig wants slashes and no backslashes
DTK_S := $(shell cygpath -m "$(ACULAB_ROOT)")

# CC := cl /MD
CC := gcc -mno-cygwin # -g

# check for our standard locations of SWIG and Python

SWIG := $(dir $(strip $(wildcard c:/swig-1.3.36/swig.exe) \
                      $(wildcard d:/swig-1.3.36/swig.exe) \
                      $(wildcard e:/swig-1.3.36/swig.exe) \
                      $(wildcard c:/swigwin-1.3.36/swig.exe) \
                      $(wildcard d:/swigwin-1.3.36/swig.exe) \
                      $(wildcard e:/swigwin-1.3.36/swig.exe)))swig

PYTHON := $(strip $(wildcard c:/python26/python.exe) \
			      $(wildcard d:/python26/python.exe) \
                  $(wildcard e:/python26/python.exe))

DEFINES := -D_WIN32 -DWIN32 -DTiNG_USE_V6 -DTiNGTYPE_WINNT
C_DEFINES := $(DEFINES)

ACULAB_INCLUDE =  -I$(DTK_S)/include -I$(DTK_S)/TiNG/pubdoc/gen \
                  -I$(DTK_S)/TiNG/apilib -I$(DTK_S)/TiNG/apilib/WINNT \
                  -I$(DTK_S)/TiNG/include

# Determine Python paths and version from installed python executable via 
# distutils. 

PYTHON_INCLUDE := -I$(shell cygpath -u "$(shell $(PYTHON) disthelper.py -i)")
# avoid multiple warnings if python is not found
ifneq ($(PYTHON_INCLUDE),) 
PYTHON_LIBDIR := 
PL = $(shell cygpath -u "$(shell $(PYTHON) disthelper.py -L)")
PYTHON_VERSION := $(subst .,,$(shell $(PYTHON) disthelper.py -v))
PYTHON_LIBS := $(PL)/libpython$(PYTHON_VERSION).a
PYTHON_SITEDIR := $(shell $(PYTHON) disthelper.py -l)
endif

ACULAB_LIBDIR := -L$(DTK)/lib
ACULAB_LIBS := -lcl_lib -lres_lib -lsw_lib -lrmsm -lTiNG -lws2_32

LDFLAGS := -shared -s
POST_LDFLAGS := 

OBJS := lowlevel_wrap$(O) 



