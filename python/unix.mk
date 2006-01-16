O := .o
A := .a
SO := .so

DTK := $(ACULAB_ROOT)
FAX := ProsodyLibraries/Group3fax_LINUX_V6_rel321/API

CC := gcc

SWIG := swig
PYTHON := python

PYTHON_INCLUDE := -I$(firstword $(strip \
			   	      $(wildcard /usr/local/include/python2.4) \
                      $(wildcard /usr/include/python2.4)))

PYTHON_LIBDIR := -L$(firstword $(strip \
                     $(wildcard /usr/local/lib/python2.4/config/) \
                     $(wildcard /usr/lib/python2.4/config/)))

PYTHON_LIBS = -lpython2.4

TiNGTYPE := LINUX
DEFINES := -DACU_LINUX -DSM_POLL_UNIX -DTiNGTYPE_$(TiNGTYPE) -DTiNG_USE_V6
C_DEFINES := -g -DNDEBUG -D_REENTRANT -fPIC $(DEFINES)

ACULAB_INCLUDE = -I$(DTK)/include -I$(DTK)/ting/include -I$(DTK)/$(FAX)/include
ACULAB_LIBDIR = -L$(DTK)/lib -L$(DTK)/ting/lib
ACULAB_LIBS = -lacu_cl -lacu_sw -lacu_res -lacu_common -lTiNG -lstdc++

LDFLAGS := -g -shared

OBJS := lowlevel_wrap.o

EXTRA_OBJS = -Xlinker -R$(DTK)/lib -L$(DTK)/lib \
			$(DTK)/$(FAX)/lib/actiff.o $(DTK)/$(FAX)/lib/faxlib.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/aculog.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/vseprintf.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfile.o \
			$(DTK)/ting/libutil/gen-$(TiNGTYPE)_V6/bfopen.o
