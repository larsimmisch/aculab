#ifdef SM_POLL_UNIX
%extend tSMEventId {
	int fileno() {
		return self->fd;
	}
};
#endif

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
		self->length = PyString_GET_SIZE(s);
		if (self->length > maxsize)
		{
			printf("boohoo\n");
	    	PyErr_Format(PyExc_ValueError, "max size(%d) exceeded",
						 maxsize);
			return;
		}
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

	PyObject *getdata() {
		return PyBuffer_FromMemory(self->data, self->length);
	}
}

