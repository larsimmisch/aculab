O := .o
A := .a
SO := .so

DTK := $(ACULAB_ROOT)

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

# TiNGTYPE := LINUX
DEFINES := -DUNIX_SYSTEM -DSM_POLL_UNIX # -DTiNGTYPE_$(TiNGTYPE) -DHAVE_TiNG
C_DEFINES := -g -DNDEBUG -D_REENTRANT -fPIC $(DEFINES)

ACULAB_INCLUDE = -I$(DTK)/call/include -I$(DTK)/switch/include \
	-I$(DTK)/speech/include
ACULAB_LIBDIR = -L$(DTK)/call/lib -L$(DTK)/switch/lib -L$(DTK)/speech/lib
ACULAB_LIBS = -lmvcl -lmvsw -lmvsm

LDFLAGS := -g -shared

OBJS := lowlevel_wrap.o
