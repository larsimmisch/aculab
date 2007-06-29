#!/usr/bin/env python

import unittest
from aculab.error import AculabError, AculabSpeechError

class ErrorTest(unittest.TestCase):
    """Check formatting and name resolution of Aculab errors."""

    def raise_error(self, e):
        raise e

    def testAErrorBasic(self):
        'Raise an Aculab error'
        self.assertRaises(AculabError, self.raise_error, AculabError(-2))

    def testAErrorDesc(self):
        'AculabError: check description (no function name)'
        try:
            raise AculabError(-2)
        except AculabError, e:
            self.failUnless(e.desc == 'unknown failed: ERR_HANDLE')

    def testAErrorDescF(self):
        'AculabError: check description (with function name)'
        try:
            raise AculabError(-2, 'foo')
        except AculabError, e:
            self.failUnless(e.desc == 'foo failed: ERR_HANDLE')

    def testAErrorDescFN(self):
        '''AculabError: check description (with function and name)'''
        try:
            raise AculabError(-2, 'foo', 'cc-1234')
        except AculabError, e:
            self.failUnless(e.desc == 'cc-1234 foo failed: ERR_HANDLE')

    def testAErrorValue(self):
        'AculabError: check the value'
        try:
            raise AculabError(-2)
        except AculabError, e:
            self.failUnless(e.value == -2)

    def testSErrorDescFN(self):
        '''AculabSpeechError: check description (with function and name)'''
        try:
            raise AculabSpeechError(-116, 'foo', 'sc-4321')
        except AculabSpeechError, e:
            self.failUnless(
                e.desc == 'sc-4321 foo failed: ERR_SM_WRONG_CHANNEL_STATE')

if __name__ == '__main__':
    unittest.main()
