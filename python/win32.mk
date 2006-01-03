O := .obj
SO := .dll
EXP := .exp
CRUFT := *.opt *.plg *.ncb

DTK := $(dir $(strip $(wildcard c:/Aculab/API/Call) \
                     $(wildcard c:/Programs/Aculab/API/Call) \
                     $(wildcard c:/Programme/Aculab/API/Call)))

CC := cl /MD

# check for our standard locations of SWIG and Python

SWIG := $(dir $(strip $(wildcard c:/swig-1.3.21/swig.exe) \
                      $(wildcard d:/swig-1.3.21/swig.exe) \
                      $(wildcard e:/swig-1.3.21/swig.exe)))swig

PYTHON := $(dir $(strip $(wildcard c:/python24/python.exe) \
                        $(wildcard d:/python24/python.exe) \
                        $(wildcard e:/python24/python.exe)))

DEFINES := -DWIN32
C_DEFINES := $(DEFINES)

ACULAB_INCLUDE = -I$(DTK)Call/include -I$(DTK)Switch/include \
	-I$(DTK)Speech/include
PYTHON_INCLUDE = -I$(PYTHON)include
PYTHON_LIBS	= $(PYTHON)libs/python24.lib advapi32.lib

LDFLAGS := /LD
POST_LDFLAGS := /link /EXPORT:init_lowlevel

OBJS := lowlevel_wrap$(O) cllib$(O) clnt$(O) common$(O) swlib$(O) swnt$(O) \
			smnt$(O) smbesp$(O) smlib$(O) smfwcaps$(O)

%$(O): ../src/%.c
	$(CC) -c $(C_DEFINES) $(ACULAB_INCLUDE) $(PYTHON_INCLUDE) $< -o $@ 

