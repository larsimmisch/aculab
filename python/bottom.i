%extend SM_TS_DATA_PARMS {
	PyObject *getdata() {
		return PyString_FromStringAndSize(self->data, self->length);
	}

	void initrecordbuffer() {
		if (self->data)
			free(self->data);

		self->data = malloc(kSMMaxRecordDataBufferSize);
		self->length = kSMMaxRecordDataBufferSize;
	}
}

%extend RAW_DATA_STRUCT {
	PyObject *getdata() {
		return PyString_FromStringAndSize(self->data, self->length);
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
