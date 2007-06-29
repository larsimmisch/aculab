O := .o
A := .a
SO := .so

DTK := $(ACULAB_ROOT)
FAX := ProsodyLibraries/Group3Fax/API

HAVE_FAX := $(strip $(wildcard $(DTK)/$(FAX)/include))

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

TiNGTYPE := LINUX
DEFINES := -DACU_LINUX -DSM_POLL_UNIX -DTiNGTYPE_$(TiNGTYPE) -DTiNG_USE_V6 
ifneq ($(HAVE_FAX),)
DEFINES += -DHAVE_FAX
endif
SWIG_DEFINES := -DTiNG_USE_UNDECORATED_NAMES
C_DEFINES := -g -DNDEBUG -D_REENTRANT -fPIC $(DEFINES)


ACULAB_INCLUDE = -I$(DTK)/include -I$(DTK)/TiNG/pubdoc/gen -I$(DTK)/$(FAX)/include -I$(DTK)/TiNG/apilib -I$(DTK)/TiNG/apilib/POSIX -I$(DTK)/TiNG/apilib/LINUX -I$(DTK)/TiNG/include
ACULAB_LIBDIR = -L$(DTK)/lib -L$(DTK)/TiNG/lib
ACULAB_LIBS = -lacu_cl -lacu_sw -lacu_res -lacu_common -lTiNG 

ifneq ($(HAVE_FAX),)
ACULAB_LIBDIR += -L$(DTK)/$(FAX)/lib
ACULAB_LIBS += -lfaxlib -lactiff -lfontconfig -lstdc++
endif

LDFLAGS := -g -shared

OBJS := lowlevel_wrap.o

ifeq ($(HAVE_FAX),)
EXTRA_OBJS = -Xlinker -R$(DTK)/lib
else
EXTRA_OBJS =  $(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/aculog.o \
              $(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/vseprintf.o \
              $(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfile.o \
              $(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfopen.o \
			  -Xlinker -R$(DTK)/lib  \

endif
