"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from question.models import QTemplate


class SimpleTests(TestCase):
    fixtures = ['question_testdata.json',]
    def test_loading_of_tests(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        q = QTemplate.objects.all().filter(name='Basic multiplication')
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0].difficulty, 3)

