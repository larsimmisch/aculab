O := .o
A := .a
SO := .so

DTK := $(ACULAB_ROOT)

CC := gcc

SWIG := swig
PYTHON := python

# Determine Python paths and version from installed python executable via 
# distutils. 
PYTHON_INCLUDE := -I$(shell $(PYTHON) install.py -i)
# avoid multiple warnings if python is not found
ifneq ($(PYTHON_INCLUDE),) 
PYTHON_LIBDIR := -L$(shell $(PYTHON) install.py -L)
PYTHON_VERSION := $(shell $(PYTHON) install.py -v)
PYTHON_LIBS := -lpython$(PYTHON_VERSION)
PYTHON_SITEDIR := $(shell $(PYTHON) install.py -l)
endif


# TiNGTYPE := LINUX
DEFINES := -DUNIX_SYSTEM -DSM_POLL_UNIX # -DTiNGTYPE_$(TiNGTYPE) -DHAVE_TiNG
C_DEFINES := -g -DNDEBUG -D_REENTRANT -fPIC $(DEFINES)

ACULAB_INCLUDE = -I$(DTK)/call/include -I$(DTK)/switch/include \
	-I$(DTK)/speech/include
ACULAB_LIBDIR = -L$(DTK)/call/lib -L$(DTK)/switch/lib -L$(DTK)/speech/lib
ACULAB_LIBS = -lmvcl -lmvsw -lmvsm

LDFLAGS := -g -shared

OBJS := lowlevel_wrap.o
