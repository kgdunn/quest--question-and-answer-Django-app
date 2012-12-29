"""
Another method of debugging Django is to use wingdbstub.py to initiate
debugging when Django is started from outside of Wing IDE. This will allow
Django to restart automatically after code changes and to automatically
reconnect the debugger to Wing IDE as needed.

This is done by placing a copy of wingdbstub.py, which is located in your
Wing IDE installation directory, in the top of the Django directory, where
manage.py is located. Make sure that WINGHOME is set inside wingdbstub.py;
if not, set it to the location of your Wing IDE installation (or on OS X,
the Contents/MacOS folder within the .app folder). This allows the debug
process to find the debugger implementation.

Next, place the following code into files you wish to debug:
import wingdbstub
Then make sure that the Enable Passive Listen preference is enabled in Wing
and start Django. The Django process should connect to Wing IDE and stop at
any breakpoints set after the import wingdbstub.

When code is changed, just save it and Django will restart. The debugger will
reconnect to Wing IDE once you request a page load in your browser that leads
to one of your import wingdbstub statements.
"""
import wingdbstub
from django.test import TestCase
from question.models import QTemplate


class SimpleTests(TestCase):
    fixtures = ['initial_data', 'question_testdata.json',]
    def test_loading_of_tests(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        q = QTemplate.objects.all().filter(name='Basic multiplication')
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0].difficulty, 3)

class ParseTests(TestCase):
    fixtures = ['initial_data', 'question_testdata.json',]
    def test_mcq_tests(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        some_text = """Type: MCQ
        --
        If a=1, b=2. What is a*b?
        --
        & 12
        & 1
        ^2
        & 4
        --"""
        from views import parse_question_text
        parse_question_text(some_text)




