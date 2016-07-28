# -*- coding: utf-8 -*-
from unittest import TestCase
import resource

from problemtools.run import limit


class Limit_test(TestCase):
    def test_less(self):
        less = limit.__dict__['__limit_less']
        assert less(42, 42)
        assert not less(42, 41)
        assert less(1e99, resource.RLIM_INFINITY)
        assert less(resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        assert not less(resource.RLIM_INFINITY, 1e99)
