%module aculab
%{
#include "mvcldrvr.h"
#include "mvswdrvr.h"
#include "smport.h"
#include "smdrvr.h"
#include "smbesp.h"
#include "smfwcaps.h"

/*
  Macro to create a SWIG-compatible pointer-type string from a base type
*/
#define SWIGTYPE(X) SWIGTYPE_##X

%}

%import "smport.h"

/*
%typemap(python,except) int {
    $function

	if ($source)
	{
	    PyErr_SetString(PyExc_RuntimeError, error_2_string($source));
    	return NULL;
  	}
}
*/