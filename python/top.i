%module lowlevel
%{
#include "mvcldrvr.h"
#include "mvswdrvr.h"
#include "smport.h"
#ifndef WIN32
#include "smosintf.h"
#endif
#include "smdrvr.h"
#include "smbesp.h"
#include "smfwcaps.h"

/*
  Macro to create a SWIG-compatible pointer-type string from a base type
*/
#define MAKE_SWIGTYPE(X) SWIGTYPE_p_##X

%}

/* Allows to execute Python code during function calls */
%define BLOCKING(name) 
%exception name {
	PyThreadState *tstate = PyEval_SaveThread();
	$function
	PyEval_RestoreThread(tstate);
}
%enddef

/* This list was manually created from all structures that:
   - have a timeout member
   - are used in a function call

   It might become incomplete in future versions
*/
BLOCKING(call_event)
BLOCKING(call_state)
BLOCKING(call_details)
BLOCKING(call_send_q921)
BLOCKING(call_get_q921)
BLOCKING(call_watchdog)
BLOCKING(dpns_call_details)
BLOCKING(dpns_send_transit)
BLOCKING(dpns_transit_details)
BLOCKING(dpns_set_l2_ch)
BLOCKING(dpns_l2_state)
BLOCKING(dpns_watchdog)

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
