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
