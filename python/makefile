# makefile for aculab swig wrapper
# just does a test for the host operating system and includes
# a sub-makefile that does the work

# check for signs of Unix
find_init := $(strip $(wildcard /sbin/init) \
	                     $(wildcard /usr/sbin/init) \
	 	                 $(wildcard /hurd/auth))

# include the appropriate sub-makefile
ifeq ($(find_init),)
  include makefile.win32
else
  include makefile.unix
endif # test is_unix
