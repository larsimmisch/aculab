O := .o
A := .a
SO := .so

DTK := $(ACULAB_ROOT)
FAX := ProsodyLibraries/Group3Fax/API

CC := gcc

SWIG := swig
PYTHON := python

PYTHON_V24 := $(strip $(wildcard /usr/local/include/python2.4) \
                      $(wildcard /usr/include/python2.4))


PYTHON_INCLUDE := -I$(firstword $(strip \
			   	      $(wildcard /usr/local/include/python2.3) \
                      $(wildcard /usr/include/python2.3) \
			   	      $(wildcard /usr/local/include/python2.4) \
                      $(wildcard /usr/include/python2.4)))

PYTHON_LIBDIR := -L$(firstword $(strip \
                     $(wildcard /usr/local/lib/python2.3/config/) \
                     $(wildcard /usr/lib/python2.3/config/) \
                     $(wildcard /usr/local/lib/python2.4/config/) \
                     $(wildcard /usr/lib/python2.4/config/)))

ifneq ($(PYTHON_V24),)
PYTHON_LIBS = -lpython2.4
else
PYTHON_LIBS = -lpython2.3
endif

TiNGTYPE := LINUX
DEFINES := -DACU_LINUX -DSM_POLL_UNIX -DTiNGTYPE_$(TiNGTYPE) -DTiNG_USE_V6 -DPROSODY_TiNG
SWIG_DEFINES := -DTiNG_USE_UNDECORATED_NAMES
C_DEFINES := -g -DNDEBUG -D_REENTRANT -fPIC $(DEFINES)

ACULAB_INCLUDE = -I$(DTK)/include -I$(DTK)/TiNG/pubdoc/gen -I$(DTK)/$(FAX)/include -I$(DTK)/TiNG/apilib -I$(DTK)/TiNG/apilib/LINUX -I$(DTK)/TiNG/include
ACULAB_LIBDIR = -L$(DTK)/lib -L$(DTK)/TiNG/lib
ACULAB_LIBS = -lacu_cl -lacu_sw -lacu_res -lacu_common -lTiNG -lacu_rmsm -lstdc++

LDFLAGS := -g -shared

OBJS := lowlevel_wrap.o

ifeq ($(HAVE_FAX),)
EXTRA_OBJS = -Xlinker -R$(DTK)/lib -L$(DTK)/lib
else
EXTRA_OBJS = -Xlinker -R$(DTK)/lib -L$(DTK)/lib \
			$(DTK)/$(FAX)/lib/actiff.o $(DTK)/$(FAX)/lib/faxlib.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/aculog.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/vseprintf.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfile.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfopen.o
endif
