%module lowlevel
%{
#include "mvcldrvr.h"
#include "mvswdrvr.h"
#include "smdrvr.h"
#ifndef HAVE_TiNG
#include "smport.h"
#include "smosintf.h"
#endif
#include "smbesp.h"

/*
  Macro to create a SWIG-compatible pointer-type string from a base type
*/
#define MAKE_SWIGTYPE(X) SWIGTYPE_p_##X

%}

#ifndef HAVE_TiNG
%include "smport.h"
#endif

/* Allows to execute Python code during function calls */
%define BLOCKING(name) 
%exception name {
	PyThreadState *tstate = PyEval_SaveThread();
	$function
	PyEval_RestoreThread(tstate);
}
%enddef

/* This list was manually created (for version 5.10.0) from all structures 
   that:
   - have a timeout member
   - are used in a function call

   It might become incomplete in future versions.
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

/* Functions that are in Aculab's headers, but not implemented.

  In other words, ignore the cruft.
*/
%ignore chknet_port;
%ignore chknet;
%ignore call_assoc_net;
%ignore call_l1_stats;
%ignore call_l2_state;
%ignore call_br_l1_stats;
%ignore call_br_l2_state;

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
