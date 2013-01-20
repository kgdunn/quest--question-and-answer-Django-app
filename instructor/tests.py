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
from question.models import QTemplate, QSet, QActual
from person.models import User
from course.models import Course
import views
from views import render

# For all tests:
course = Course.objects.all()[0]
user = User.objects.all()[0]


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
    def test_mcq_basic_parse(self):
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

    def test_long_answer_entry(self):
        """
        More complete template
        """
        some_text = """
[[type]]
long

[[attribs]]
Contributor: Kevin Dunn
Difficulty: 3
Grade: 5

[[question]]
Your statistical pre-requisite course was taken a few years ago;
tell us your thoughts about that course.

[[grading]]
Full grade for any reasonable answer. Our aim is to collect feedback.

[[solution]]
There is no solution for this question.
"""
        qtemplate = views.create_question_template(some_text)
        q = QTemplate.objects.get(id=qtemplate.id)
        self.assertEqual(q.difficulty, 3)
        self.assertEqual(q.max_grade, 5)
        self.assertEqual(q.t_solution, ('There is no solution for this '
                                         'question.'))
        #self.assertEqual(q.t_question,

    def test_short_answer_question(self):
        """
        Template test for a short answer question
        """
        some_text = """
[[type]]
short
[[question]]

Plots with both category and value axes are known as {[ans1]} plots, while a
plot with the 5-number summary of a univariate series are called {[2]} plots.
[[grading]]
ans1:bar
ans1:BAR
2:box
[[solution]]
Goes here
[[attribs]]
Contributor: Kevin Dunn
Difficulty: 1
Tags: data visualization
Grade: 1
"""
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        self.assertEqual(qt.t_solution, u'Goes here')
        t_grading = json.loads(qt.t_grading)
        vals = t_grading.values()
        keys = t_grading.keys()
        self.assertEqual(keys, ['ans1', '2']) # <--- keys are strings
        self.assertEqual(vals, [['bar', 'BAR'], ['box']])
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)
        self.assertEqual(qa.as_displayed[0:74], ('<p>Plots with both category '
                            'and value axes are known as <input type="text"'))


    def test_variables_with_choices(self):
        some_text="""
[[type]]
multipart
[[question]]
Plot a time series plot using rows {{row_start}} to
{% quick_eval "row_start+1000" %} for the `{{variable_name}}` variable.
Save the plot as a JPEG or PNG file and upload it here {[:upload:]}
[[variables]]
row_start:[1, 2000, 100, int]
variable_name: {'choices': ['Opt1', 'Opt2', 'Opt3']}
[[solution]]
Some solution text would go here.
[[grading]]
Some grading text would go here.
        """
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)
        start = qa.as_displayed.find('for the <code>')
        self.assertTrue(qa.as_displayed[start+14:start+18] in ('Opt1', 'Opt2', 'Opt3'))


    def test_question_missing_variable(self):
        some_text = """
[[type]]
multi
[[question]]
Our process produces defective products at a rate of 1 in {{n_total}}. If we randomly take a sample of {{n_sample}} items from the production line,then ....
--
^{% quick_eval "((n_total-1)/n_total)**n_sample" %}
& {% quick_eval "((n_total-1)/n_total)" %}
& be greater than or equal to ({{n_total}}-1)/{{n_total}})
& is equal to 1/{{n_total}}
[[variables]]
n_total: [6, 10, 1, int]
n: [4,6,1,int]
[[Solution]]
The pass rate for this system is ({{n_total}}-1)/{{n_total}}), so
"""
        # The ``n_sample`` variable is not specified
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        qset = QSet.objects.create(name="temporary", course=course)

        with self.assertRaises(NameError):
            qa = render(qt, qset, user)


    def test_dont_allow_no_answers_MCQ(self):
        """
        [[type]]
        multi
        [[question]]
        The following plot is from a measurement system at a company showing actual data   PLOT HERE
        Some of the things that can be noticed in the plot are:
        --
        &
        ^
        """




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
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)

        key, value = views.get_type(qt.t_grading, 'key').next()
        self.assertTrue(key.startswith('True'))
        start = qa.as_displayed.find(value)
        self.assertEqual(qa.as_displayed[start+7:start+11], 'True')

        key, value = views.get_type(qt.t_grading, 'lure').next()
        self.assertTrue(key.startswith('False'))
        start = qa.as_displayed.find(value)
        self.assertEqual(qa.as_displayed[start+7:start+12], 'False')


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
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)

        key, value = views.get_type(qt.t_grading, 'final-lure').next()
        self.assertTrue(key.startswith('None of the above.'))
        start = qa.as_displayed.find(value)
        self.assertEqual(qa.as_displayed[start+7:start+11], 'None')


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
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)

        key, value = views.get_type(qt.t_grading, 'final-key').next()
        self.assertTrue(key.startswith('None of the above.'))
        start = qa.as_displayed.find(value)
        self.assertEqual(qa.as_displayed[start+7:start+11], 'None')
        self.assertEqual(qt.t_solution, ('The solution is: "None of the '
                                         'above."'))


    def test_mcq_basic(self):
        """
        Basic question template. Really the minimal possible example.

        NOTE: it would be much cleaner to have
                    {{ a+b |quick_eval }}
              instead of
                    {% quick_eval "a+b" %}
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
^{% quick_eval "a*b" 5 %}
& {% quick_eval "a+b" 2 %}
[[variables]]
a: [2, 5, 0.5, float]
b: [5, 9, 1, int]
        """
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)
        qa = QActual.objects.get(id=qa.id)
        var_dict = json.loads(qa.var_dict)
        true_answer = var_dict['a'][1] * var_dict['b'][1]
        self.assertEqual(qa.html_solution, '<p>The solution is: "%s"</p>' %\
                         true_answer)


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


    def test_image_location(self):
        """
        Tests that images are placed in the correct location
        """

        some_text = """
[[type]]
TF
[[question]]
The image here contains oscillations
![Image alt text](image_file_name.jpg)
--
& False
^ True
"""
        qtemplate = views.create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)
        qset = QSet.objects.create(name="temporary", course=course)

        qa = render(qt, qset, user)
        idx = qa.as_displayed.find('image_file_name.jpg')
        self.assertEqual(qa.as_displayed[idx-3:idx], '/0/') # this is the subdir stored in
