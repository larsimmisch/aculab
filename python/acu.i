%module lowlevel
%{
#include "cl_lib.h"
#include "res_lib.h"
#include "sw_lib.h"
#include "smdrvr.h"
#include "smbesp.h"
#include "smfaxapi.h"
#include "actiff.h"
#include "smdc.h"
#include "smdc_raw.h"
#include "smdc_sync.h"
#include "smdc_hdlc.h"

/*
  Macro to create a SWIG-compatible pointer-type string from a base type
*/
#define MAKE_SWIGTYPE(X) SWIGTYPE_p_##X

%}

// %include "typemaps.i"

/* Fake an ACTIFF_PAGE_HANDLE (which is just a typedef for void - nasty!) */
typedef struct {
} ACTIFF_PAGE_HANDLE;

%extend ACTIFF_PAGE_HANDLE {
	ACTIFF_PAGE_HANDLE() {
		return (ACTIFF_PAGE_HANDLE*) calloc(1,sizeof(ACTIFF_PAGE_HANDLE*));
	}

	~ACTIFF_PAGE_HANDLE() {
		if (self) free(self);
	}
}

%apply int { ACU_ERR, ACU_UINT, ACU_ULONG, ACU_INT, ACU_LONG, ACU_PORT_ID, 
			 ACU_CALL_HANDLE, ACU_CARD_ID, tSMCardId, ACU_RESOURCE_ID,
			 tSM_INT, tSM_UT32 };

%apply char[ANY] { ACU_CHAR[ANY] };

%apply void * { ACU_EVENT_QUEUE, ACU_ACT };

%apply (int *OUTPUT) { int *perrno };

#ifdef TiNG_USE_V6
#define cc_version 6
#else
#define cc_version 5
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
BLOCKING(smfax_rx_negotiate)
BLOCKING(smfax_tx_negotiate)
BLOCKING(smfax_rx_page)
BLOCKING(smfax_tx_page)

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
%ignore dpns_l2_state;
%ignore port_init;
%ignore call_get_global_notification_wait_object;
%ignore acu_get_aculab_directory;
%ignore sm_get_modules;
%ignore sm_get_module_card_ix;
%ignore sm_get_card_switch_ix;
%ignore sm_get_channel_module_ix;
%ignore sm_get_cards;

%ignore BFILE;

%apply char[ANY] { ACU_UCHAR[ANY] };

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
#ifdef SM_POLL_UNIX
%extend tSMEventId {
	int fileno() {
		return self->fd;
	}
};
#endif

/* typemaps for BFILE** */

%typemap(python,in,numinputs=0) BFILE** ($*1_type temp) {
	$1 = ($1_type)&temp;
}

%typemap(python,argout) BFILE** {
	$result = add_result(
		$result, SWIG_NewPointerObj(*$1, SWIGTYPE_p_BFILE, 1));
}

%include "cl_lib.h2"
%include "res_lib.h2"
%include "sw_lib.h"
%include "smdrvr.h"
%include "smbesp.h"
%include "actiff.h"
%include "smdc.h"
%include "smdc_raw.h"
%include "smdc_sync.h"
%include "smdc_hdlc.h"
%include "bfile.h2"
%include "bfopen.h"
%include "smfaxapi.h"


/* Use macro this for structures with data and length members, where data must
   be copied into the structure (as opposed to: the data pointer must be set) 
*/
%define GET_SET_DATA(name, maxsize) 
%extend name {
	PyObject *getdata() {
		return PyString_FromStringAndSize((const char*)self->data, 
										  self->length);
	}

	void setdata(PyObject *s) {
		if (!PyString_Check(s)) {
	    	PyErr_SetString(PyExc_TypeError,"Expected a string");
			return;
		}
		if (PyString_GET_SIZE(s) > maxsize)
		{
	    	PyErr_SetString(PyExc_ValueError, 
							"max size for name.data exceeded");
			return;
		}
		self->length = PyString_GET_SIZE(s);
		memcpy(self->data, PyString_AS_STRING(s), self->length);
	}
};
%enddef

GET_SET_DATA(RAW_DATA_STRUCT, MAXRAWDATA)
GET_SET_DATA(FACILITY_XPARMS, MAXFACILITY_INFO)
GET_SET_DATA(UUI_XPARMS, MAXUUI_INFO)
GET_SET_DATA(NON_STANDARD_DATA_XPARMS, MAXRAWDATA)

%extend SM_TS_DATA_PARMS {
	void allocrecordbuffer()
	{
		self->data = (char*)malloc(kSMMaxRecordDataBufferSize);
		self->length = kSMMaxRecordDataBufferSize;
	}

	void freerecordbuffer()
	{
		free(self->data);
	}

	void setdata(PyObject *s) {
		if (!PyString_Check(s)) {
	    	PyErr_SetString(PyExc_TypeError,"Expected a string");
			return;
		}
		if (PyString_GET_SIZE(s) > kSMMaxReplayDataBufferSize)
		{
	    	PyErr_SetString(PyExc_ValueError, 
							"max size for name.data exceeded");
			return;
		}
		self->length = PyString_GET_SIZE(s);
		self->data = PyString_AS_STRING(s);
	}
	

	PyObject *getdata() {
		return PyBuffer_FromMemory(self->data, self->length);
	}
}

%extend ACU_SNAPSHOT_PARMS {
    ACU_SNAPSHOT_PARMS() {
		ACU_SNAPSHOT_PARMS *v = 
			(ACU_SNAPSHOT_PARMS*)calloc(1, sizeof(ACU_SNAPSHOT_PARMS));
		v->size = sizeof(ACU_SNAPSHOT_PARMS);
		return v;
    }
    ~ACU_SNAPSHOT_PARMS() {
		free(self);
    }
	char *get_serial(int i) {
		return self->serial_no[i];
	}
}

%define SIZED_STRUCT(name) 
%extend name {
    name() {
		name *v = (name*)calloc(1, sizeof(name));
		v->size = sizeof(name);
		return v;
    }
    ~name() {
		free(self);
    }
}
%enddef

#ifndef SWIGXML
%include "sized_struct.i"
#endif

%{

/*
ACTIFF_PAGE_HANDLE *new_ACTIFF_PAGE_HANDLE(){
  return (ACTIFF_PAGE_HANDLE *) calloc(1,sizeof(ACTIFF_PAGE_HANDLE*));
}
void delete_ACTIFF_PAGE_HANDLE(ACTIFF_PAGE_HANDLE *self){
  if (self) free(self);
}
*/

PyObject *add_result(PyObject *result, PyObject *o)
{
	if ((!result) || (result == Py_None)) 
	{
		return o;
	} 

	if (!PyList_Check(result)) 
	{
		PyObject *o2 = result;
		result = PyList_New(0);
		PyList_Append(result,o2);
		Py_XDECREF(o2);
	}
	PyList_Append(result,o);
	Py_XDECREF(o);

	return result;
}
%}

%init %{
%}
