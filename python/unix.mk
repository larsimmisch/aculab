O := .o
A := .a
SO := .so

DTK := ../dtk111

CC := gcc

SWIG := swig
PYTHON := python

PYTHON_INCLUDES = -I/usr/include/python2.4
PYTHON_LIBDIR	= -L/usr/lib/python2.4/config
PYTHON_LIBS = -lpython2.4

# TiNGTYPE := LINUX
DEFINES := -DUNIX_SYSTEM -DSM_POLL_UNIX # -DTiNGTYPE_$(TiNGTYPE) -DHAVE_TiNG
C_DEFINES := -DNDEBUG -fPIC $(DEFINES)

ACULAB_INCLUDES = -I$(DTK)/call/include -I$(DTK)/switch/include \
	-I$(DTK)/speech/include
ACULAB_LIBDIR = -L$(DTK)/call/lib -L$(DTK)/switch/lib -L$(DTK)/speech/lib
ACULAB_LIBS = -lmvcl -lmvsw -lmvsm

LDFLAGS := -shared

OBJS := lowlevel_wrap.o
