#O := .obj
O := .o
SO := .pyd
EXP := .exp
CRUFT := *.opt *.plg *.ncb

DTK_W := $(dir $(strip $(wildcard c:/Aculab/API/Call) \
		                $(wildcard c:/Programs/Aculab/API/Call) \
						$(wildcard c:/Programme/Aculab/API/Call)))

# Need to convert to a cygwin path, otherwise the ':' in DTK will upset make
DTK := $(shell cygpath -u $(DTK_W))

# CC := cl /MD
CC := gcc -mno-cygwin

# check for our standard locations of SWIG and Python

SWIG := $(dir $(strip $(wildcard c:/swig-1.3.21/swig.exe) \
                      $(wildcard d:/swig-1.3.21/swig.exe) \
                      $(wildcard e:/swig-1.3.21/swig.exe) \
                      $(wildcard c:/swigwin-1.3.31/swig.exe) \
                      $(wildcard d:/swigwin-1.3.31/swig.exe) \
                      $(wildcard e:/swigwin-1.3.31/swig.exe)))swig

PYTHON := $(strip $(wildcard c:/python25/python.exe) \
			      $(wildcard d:/python25/python.exe) \
                  $(wildcard e:/python25/python.exe))

DEFINES := -DWIN32 
C_DEFINES := $(DEFINES)

SWIG_INCLUDE = -I$(DTK_W)Call/include -I$(DTK_W)Switch/include \
	-I$(DTK_W)Speech/include

ACULAB_INCLUDE = -I$(DTK)Call/include -I$(DTK)Switch/include \
	-I$(DTK)Speech/include

# Determine Python paths and version from installed python executable via 
# distutils. 

PYTHON_INCLUDE := -I$(shell cygpath -u $(shell $(PYTHON) disthelper.py -i))
# avoid multiple warnings if python is not found
ifneq ($(PYTHON_INCLUDE),) 
PYTHON_LIBDIR := -L$(shell cygpath -u $(shell $(PYTHON) disthelper.py -L))
PYTHON_VERSION := $(shell $(PYTHON) disthelper.py -v)
PYTHON_LIBS := -lpython$(PYTHON_VERSION)
PYTHON_SITEDIR := $(shell $(PYTHON) disthelper.py -l)
endif

LDFLAGS := -shared -s
POST_LDFLAGS := 

OBJS := lowlevel_wrap$(O) set_inaddr${O} cllib$(O) clnt$(O) common$(O) \
	swlib$(O) swnt$(O) smnt$(O) smbesp$(O) smlib$(O) smfwcaps$(O)

%$(O): ../src/%.c
	$(CC) -c $(C_DEFINES) $(ACULAB_INCLUDE) $(PYTHON_INCLUDE) $< -o $@ 

