#ifdef SM_POLL_UNIX
%extend tSMEventId {
	int fileno() {
		return self->fd;
	}
};
#endif

%extend SM_TS_DATA_PARMS {
	PyObject *getdata() {
		return PyString_FromStringAndSize((const char*)self->data, 
										  self->length);
	}

	void initrecordbuffer() {
		if (self->data)
			free(self->data);

		self->data = (char*)malloc(kSMMaxRecordDataBufferSize);
		self->length = kSMMaxRecordDataBufferSize;
	}
}

%extend RAW_DATA_STRUCT {
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
		memcpy(self->data, PyString_AS_STRING(s), self->length);
	}
}
