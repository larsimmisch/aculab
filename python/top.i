%module lowlevel
%{
#include "mvcldrvr.h"
#include "mvswdrvr.h"
#include "smport.h"
#include "smosintf.h"
#include "smdrvr.h"
#include "smbesp.h"
#include "smfwcaps.h"

/*
  Macro to create a SWIG-compatible pointer-type string from a base type
*/
#define MAKE_SWIGTYPE(X) SWIGTYPE_p_##X

%}

/* This allows to execute Python code during the function call. */
%exception {
	PyThreadState *tstate = PyEval_SaveThread();
	$function
	PyEval_RestoreThread(tstate);
}

#ifdef WIN32
%typemap(python,in) tSMEventId {
	$1 = (tSMEventId)PyInt_AsLong($input);
}

%typemap(python,in,numinputs=0) tSMEventId * ($basetype temp) {
	$1 = ($basetype*)&temp;
}

%typemap(python,argout) tSMEventId * {
	PyObject *o = PyInt_FromLong((unsigned)*$1);
	if ((!$result) || ($result == Py_None)) 
	{
		$result = o;
    } 
	else 
	{
		if (!PyList_Check($result)) 
		{
			PyObject *o2 = $result;
			$result = PyList_New(0);
			PyList_Append($result,o2);
			Py_XDECREF(o2);
		}
		PyList_Append($result,o);
		Py_XDECREF(o);
	}
}
#endif

/*
%typemap(python,except) int {
    $function

	if ($1)
	{
	    PyErr_SetString(PyExc_RuntimeError, error_2_string($1));
    	return NULL;
  	}
}
*/
