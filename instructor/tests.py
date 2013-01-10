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

# TODO: sign in user and make sure they only see the questions they
#       are supposed to see, i.e. not the full question set, just the subset

try:
    import simplejson as json
except ImportError:
    import json

import wingdbstub
from django.test import TestCase
from question.models import QTemplate
import views


class SimpleTests(TestCase):
    fixtures = ['initial_data',]
    def test_loading_of_tests_from_fixtures(self):
        """
        Loaded from fixture
        """
        q = QTemplate.objects.all().filter(name='Basic multiplication')
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0].difficulty, 3)

class ParseTests(TestCase):
    fixtures = ['initial_data',]
    def test_mcq_basic(self):
        """
        Basic question template. Really the minimal possible example.
        """
        some_text = """
[[type]]
MCQ
[[question]]
If a=1, b=2. What is a*b?
--
& 12
&1
^2
& 4
        """
        qtemplate = views.create_question_template(some_text)
        q = QTemplate.objects.get(id=qtemplate.id)
        self.assertEqual(q.difficulty, 1)
        self.assertEqual(q.q_type, 'mcq')
        self.assertEqual(q.name, 'If a=1, b=2. What is a*b?')


    def test_mcq_more_details(self):
        """
        More complete template
        """
        some_text = """
[[type]]
MCQ

[[attribs]]
Name: Multiplication warm-up
Contributor: Kevin Dunn
Difficulty: 2
Tags: multiplication, math
Grade: 3
Feedback: False

[[question]]
If a=1, b=2. What is a*b?
--
& 12
& 1
^2
& 4"""
        qtemplate = views.create_question_template(some_text)
        q = QTemplate.objects.get(id=qtemplate.id)
        self.assertEqual(q.difficulty, 2)
        self.assertEqual(q.max_grade, 3)
        self.assertEqual(q.enable_feedback, False)
        self.assertEqual(q.t_solution, u'The solution is: "2"')
        t_grading = json.loads(q.t_grading)
        vals = t_grading.values()
        vals.sort()
        self.assertEqual(vals, [[u'key', u'2'], [u'lure', u'1'],
                                [u'lure', u'12'], [u'lure', u'4']])

class RenderTests(TestCase):
    fixtures = ['initial_data',]
    def test_tf_basic(self):
        """
        Basic true/false template. Really the minimal possible example.
        """
        some_text = """
[[type]]
TF
[[question]]
The sun is hot.
--
& False
^True
        """
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        from views import render
        html_q, html_a, var_dict = render(qt)

        key, value = views.get_type(qt.t_grading, 'key').next()
        self.assertTrue(key.startswith('True'))
        start = html_q.find(value)
        self.assertEqual(html_q[start+6:start+10], 'True')

        key, value = views.get_type(qt.t_grading, 'lure').next()
        self.assertTrue(key.startswith('False'))
        start = html_q.find(value)
        self.assertEqual(html_q[start+6:start+11], 'False')


    def test_tf_final_incorrect(self):
        """
        Lures and an incorrect option that must be shown as the last option.
        """
        some_text = """
[[type]]
TF
[[question]]
The sun is ....
--
& Cold
& Luke warm
^ Hot
% None of the above.
        """
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        from views import render
        html_q, html_a, var_dict = render(qt)

        key, value = views.get_type(qt.t_grading, 'final-lure').next()
        self.assertTrue(key.startswith('None of the above.'))
        start = html_q.find(value)
        self.assertEqual(html_q[start+6:start+10], 'None')

    def test_tf_final_correct(self):
            """
            Lures and an CORRECT option that must be shown as the last option.
            """
            some_text = """
[[type]]
TF
[[question]]
The sun is ....
--
& Cold
& Luke warm
& Warm
%^ None of the above.
            """
            qtemplate = views.create_question_template(some_text)
            qt = QTemplate.objects.get(id=qtemplate.id)
            from views import render
            html_q, html_a, var_dict = render(qt)

            key, value = views.get_type(qt.t_grading, 'final-key').next()
            self.assertTrue(key.startswith('None of the above.'))
            start = html_q.find(value)
            self.assertEqual(html_q[start+6:start+10], 'None')
            self.assertEqual(qt.t_solution, ('The solution is: "None of the '
                                             'above."'))


    def test_mcq_basic(self):
        """
        Basic question template. Really the minimal possible example.

        NOTE: it would be much cleaner to have
                    {{ a+b |evaluate }}
              instead of
                    {% evaluate "a+b" %}
              unfortunately the former (a Django template filter) evaluates
              "a" and "b" directly and does not pass the context dictionary.
              The latter (a Django template tag) is far more powerful and
              gives us additional flexibility at render time.
        """
        some_text = """
[[type]]
MCQ
[[question]]
If a={{a}}, b={{b}}. What is a*b?
--
& {{a}}{{b}}
&1
^{% evaluate "a*b" %}
& {% evaluate "a+b" %}
[[variables]]
a: [2, 5, 0.5, float]
b: [5, 9, 1, int]
        """
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        from views import render
        html_q, html_a, var_dict = render(qt)


    def test_mcq_bad_specified(self):
        """
        Two correct options for an MCQ.
        """
        some_text = """
[[type]]
MCQ
[[question]]
The sun is ....
--
^ Cold
& Luke warm
^ Hot
% None of the above.
        """
        with self.assertRaises(views.ParseError):
            views.create_question_template(some_text)

    def test_mcq_bad_specified(self):
        """
        Two correct options for an MCQ.
        """
        some_text = """
[[type]]
MCQ
[[question]]
The sun is ....
--
^ Cold
& Luke warm
^ Hot
% None of the above.
        """
        with self.assertRaises(views.ParseError):
            views.create_question_template(some_text)
