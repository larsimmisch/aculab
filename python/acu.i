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

unsigned char bitrev[] = {
	0x00, 0x80, 0x40, 0xc0, 0x20, 0xa0, 0x60, 0xe0, 0x10, 0x90, 0x50, 0xd0, 
	0x30, 0xb0, 0x70, 0xf0,	0x08, 0x88, 0x48, 0xc8, 0x28, 0xa8, 0x68, 0xe8, 
	0x18, 0x98, 0x58, 0xd8, 0x38, 0xb8, 0x78, 0xf8, 0x04, 0x84, 0x44, 0xc4, 
	0x24, 0xa4, 0x64, 0xe4, 0x14, 0x94, 0x54, 0xd4, 0x34, 0xb4, 0x74, 0xf4,
	0x0c, 0x8c, 0x4c, 0xcc, 0x2c, 0xac, 0x6c, 0xec, 0x1c, 0x9c, 0x5c, 0xdc, 
	0x3c, 0xbc, 0x7c, 0xfc, 0x02, 0x82, 0x42, 0xc2, 0x22, 0xa2, 0x62, 0xe2, 
	0x12, 0x92, 0x52, 0xd2, 0x32, 0xb2, 0x72, 0xf2, 0x0a, 0x8a, 0x4a, 0xca, 
	0x2a, 0xaa, 0x6a, 0xea, 0x1a, 0x9a, 0x5a, 0xda, 0x3a, 0xba, 0x7a, 0xfa, 
	0x06, 0x86, 0x46, 0xc6, 0x26, 0xa6, 0x66, 0xe6, 0x16, 0x96, 0x56, 0xd6, 
	0x36, 0xb6, 0x76, 0xf6, 0x0e, 0x8e, 0x4e, 0xce, 0x2e, 0xae, 0x6e, 0xee, 
	0x1e, 0x9e, 0x5e, 0xde, 0x3e, 0xbe, 0x7e, 0xfe, 0x01, 0x81, 0x41, 0xc1, 
	0x21, 0xa1, 0x61, 0xe1, 0x11, 0x91, 0x51, 0xd1, 0x31, 0xb1, 0x71, 0xf1,
	0x09, 0x89, 0x49, 0xc9, 0x29, 0xa9, 0x69, 0xe9, 0x19, 0x99, 0x59, 0xd9, 
	0x39, 0xb9, 0x79, 0xf9, 0x05, 0x85, 0x45, 0xc5, 0x25, 0xa5, 0x65, 0xe5, 
	0x15, 0x95, 0x55, 0xd5, 0x35, 0xb5, 0x75, 0xf5, 0x0d, 0x8d, 0x4d, 0xcd, 
	0x2d, 0xad, 0x6d, 0xed, 0x1d, 0x9d, 0x5d, 0xdd, 0x3d, 0xbd, 0x7d, 0xfd,
	0x03, 0x83, 0x43, 0xc3, 0x23, 0xa3, 0x63, 0xe3, 0x13, 0x93, 0x53, 0xd3, 
	0x33, 0xb3, 0x73, 0xf3, 0x0b, 0x8b, 0x4b, 0xcb, 0x2b, 0xab, 0x6b, 0xeb, 
	0x1b, 0x9b, 0x5b, 0xdb, 0x3b, 0xbb, 0x7b, 0xfb, 0x07, 0x87, 0x47, 0xc7, 
	0x27, 0xa7, 0x67, 0xe7, 0x17, 0x97, 0x57, 0xd7, 0x37, 0xb7, 0x77, 0xf7,
	0x0f, 0x8f, 0x4f, 0xcf, 0x2f, 0xaf, 0x6f, 0xef, 0x1f, 0x9f, 0x5f, 0xdf, 
	0x3f, 0xbf, 0x7f, 0xff
};

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

%apply int { ACU_ERR, ACU_UINT, ACU_UCHAR, ACU_ULONG, ACU_INT, ACU_LONG, 
			 ACU_PORT_ID, ACU_CALL_HANDLE, ACU_CARD_ID, tSMCardId, 
             ACU_RESOURCE_ID, tSM_INT, tSM_UT32 };

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
%ignore TiNG_PRINTF_MODULE;
%ignore FORMAT_EVENT;
%ignore FORMAT_SOCKADDR_IN;

%apply char[ANY] { ACU_UCHAR[ANY] };

#ifdef WIN32
%typemap(python,in) tSMEventId {
	$1 = (tSMEventId)PyInt_AsLong($input);
}

%typemap(python,in,numinputs=0) tSMEventId * ($basetype temp) {
	$1 = ($basetype*)&temp;
}

%typemap(python,argout) tSMEventId * {
	$result = add_result($result, PyInt_FromLong((unsigned)*$1));
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

	PyObject *copy() {
		tSMEventId *temp = (tSMEventId *)calloc(1, sizeof(tSMEventId));
		memcpy(temp, self, sizeof(tSMEventId));
    
		return SWIG_NewPointerObj((void*)temp, SWIGTYPE_p_tSMEventId, 1);
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
	~SM_TS_DATA_PARMS()
	 {
		if (self->data)
		{
			free(self->data);
		}
	 }	

	void allocrecordbuffer()
	{
		self->data = (char*)malloc(kSMMaxRecordDataBufferSize);
		self->length = kSMMaxRecordDataBufferSize;
	}

	void freerecordbuffer()
	{
		if (self->data)
		{
			free(self->data);
		}
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

%extend SMDC_DATA_PARMS {
	~SMDC_DATA_PARMS()
	 {
		if (self->data)
		{
			free(self->data);
		}
	 }	

	void allocbuffer(int size)
	{
		self->data = (char*)malloc(size);
		self->max_length = size;
	}

	void freebuffer()
	{
		if (self->data)
		{
			free(self->data);
		}
	}

	PyObject *getdata() {
		return PyBuffer_FromMemory(self->data, self->done_length);
	}

	PyObject *getdata_bitrev() {
		int i;
		for (i = 0; i < self->done_length; ++i)
		{
			self->data[i] = bitrev[(unsigned char)self->data[i]];
		}
		return PyBuffer_FromMemory(self->data, self->done_length);
	}

}

%define SIZED_STRUCT(name) 
%extend name {
    name() {
		name *v = (name*)calloc(1, sizeof(name));
		v->size = sizeof(name);
		return v;
    }
	
	void clear()
	{
		memset(self, 0, sizeof(name));
		self->size = sizeof(name);
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
