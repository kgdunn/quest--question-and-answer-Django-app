import re
try:
    import simplejson as json
except ImportError:
    import json

#from django.conf import settings
#from django.core.context_processors import csrf
#from django.core.exceptions import ValidationError
#from django.template import Context, Template, Library
from django.contrib.auth.decorators import login_required
from django.shortcuts import (HttpResponse, render_to_response,
                              RequestContext)


# 3rd party imports

# Our imports
from question.models import (QTemplate, QActual, Inclusion)
from question.views import validate_user
from person.models import UserProfile
from grades.models import Grade
from utils import insert_evaluate_variables

reason_codes = {'SigFigs': 'Too many significant figures',
                'Negative MCQ': 'Lost grades for checking incorrect entries',
                'Not answered': 'Question was not answered',
                'Wrong value': 'Wrong answer given'}

negative_deduction_multi = 0.5
negative_sigfigs = 0.25


def get_auto_grader():
    """ Get the UserProfile for the ``auto-grader''
    """
    return UserProfile.objects.filter(role='Grader')[0]


@login_required                               # URL: ``grading-process-grades``
def process_grades(request, course_code_slug, question_set_slug):
    """
    Processes the grades for a given course and question set. The main entry
    point for initiating grading.

    Displays a list of students and the grades achieved.
    """
    course = validate_user(request, course_code_slug, question_set_slug,
                           admin=True)
    if isinstance(course, HttpResponse):
        return course
    if isinstance(course, tuple):
        course, qset = course

    # Iterate through all questions by all students in the QSet
    students = UserProfile.objects.filter(courses__slug=course_code_slug)
    qset_questions = QActual.objects.filter(qset__slug=question_set_slug)

    for student in students:
        for qactual in qset_questions.filter(user=student).order_by('id'):

            if qactual.grade:
                # Do not re-grade a question that has already received a grade
                continue

            if qactual.given_answer == '':
                grade = Grade.objects.create(graded_by=get_auto_grader(),
                                             approved=True,
                                             grade_value=0.0)

            elif qactual.qtemplate.q_type in ('tf', 'mcq', 'multi',):
                grade = grade_MCQ(qactual)

            elif qactual.qtemplate.q_type in ('short'):
                grade = grade_short(qactual)

            elif qactual.qtemplate.q_type in ('long'):
                grade = grade_long(qactual)

            elif qactual.qtemplate.q_type in ('numeric'):
                grade = grade_numeric(qactual)

            elif qactual.qtemplate.q_type in ('fib'):
                grade = grade_fib(qactual)

            elif qactual.qtemplate.q_type in ('multipart',):
                grade = grade_multipart(qactual)

            else:
                # TODO(KGD): else, raise an error: unspecified question type
                assert(False)

            # Save the grade
            qactual.grade = grade
            qactual.save()


    return HttpResponse('All graded')


def grade_MCQ(qactual):
    """
    Grades multiple choice questions.
    """


    reason = []

    answer = qactual.given_answer
    grading = json.loads(qactual.qtemplate.t_grading)

    grade_value = 0.0

    if qactual.qtemplate.q_type in ('tf', 'mcq',):
        # Either the person gets the answer right, or wrong.
        if grading[qactual.given_answer][0] == 'key':
            grade_value = qactual.qtemplate.max_grade
        else:
            grade_value = 0.0

    elif qactual.qtemplate.q_type in ('multi', ):

        keys = [item[0] for item in grading.items() if item[1][0]=='key']
        grade_per_key = qactual.qtemplate.max_grade / (len(keys) + 0.0)# float

        for ans in answer.split(','):
            if ans in keys:
                grade_value += grade_per_key
            elif negative_deduction_multi:
                grade_value -= negative_deduction_multi

        if grade_value != qactual.qtemplate.max_grade:
            reason.append(reason_codes['Negative MCQ'])


    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value,
                                 reason_description = reason,
                                 )

    return grade


def grade_short(qactual):
    """
    Grades short answer questions.
    """
    grade_value = 0

    #``grading_answer`` doesn't exist for the earlier quests.
    # this causes some unusual code here
    grading = json.loads(qactual.qtemplate.t_grading)
    token_dict = json.loads(qactual.given_answer)
    keys = [item[0] for item in grading.items()]
    grade_per_key = qactual.qtemplate.max_grade / (len(keys) + 0.0)

    # Main idea: compare qactual.given_answer to qactual.grading_answer
    if qactual.grading_answer:
        reason = []
        # Rather use this for ``grading``: it maps more directly
        grading = json.loads(qactual.grading_answer)
        for key, value in grading.iteritems():
            if token_dict.has_key(key):
                correct = json.loads(value[0].replace("'", '"'))
                out = compare_numeric_with_precision(correct, token_dict[key])

            else:
                out = (False, reason_codes['Not answered'])

            if out[0]:
                grade_value += grade_per_key
            else:
                reason.append(reason_codes[out[1]])

            if out[1] == 'SigFigs':
                grade_value -= negative_sigfigs
                reason.append(reason_codes['SigFigs'])

        grade = Grade.objects.create(graded_by=get_auto_grader(),
                                     approved=True,
                                     grade_value=grade_value,
                                     reason_description=reason)




    TOKEN = re.compile(r'\{\[(.*?)\]\}')
    INPUT_RE = re.compile(r'\<input(.*?)name="(.*?)"(.*?)\</input\>')

    if not qactual.grading_answer:
        if len(keys) == 1:

            # This is a quick_eval template:
            if isinstance(grading.values()[0], list):
                #deal_with_quick_eval(a
                pass

            if token_dict.values()[0].lower() in grading.values()[0]:
                grade_value = qactual.qtemplate.max_grade
            else:
                grade_value = 0
        else:
            # this is going to be messy

            html_iter = INPUT_RE.finditer(qactual.as_displayed)
            for token in TOKEN.finditer(qactual.qtemplate.t_question):
                link = html_iter.next().group(2)
                html_key = token.group(1)
                if string_match(grading[html_key],token_dict[link], qactual):
                    pass
                    #Handle sig figs here

                    #Handle other error messages here

                    #grade_value += grade_per_key

    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value)

    return grade

def deal_with_quick_eval(eval_str, given, qactual):
    """
    Given the quick_eval answer, and the given answer, makes a judgement on it,
    i.e. returns True or False if it matches to the required degree of
    significance.

    e.g. string: '[{% quick_eval "20/2.053749" 3 %},1e-2,\'rel\']'
         given:  9.76'

    """

    TAG_RE = re.compile(r'^(.*?){%(\s?)quick_eval(\s?)"(.*?)"(\s?)(\d?)(\s?)%},(\s?)(.*?),\'(.*)\'(.*)$')
    TAG_RE = re.compile(r'^(.*?){%(.*?)%},(\s?)(.*?),\'(.*)\'(.*)$')
    to_eval = '{%' + TAG_RE.search(eval_str).group(2) + '%}'
    precision = TAG_RE.search(eval_str).group(4)
    p_type = TAG_RE.search(eval_str).group(5)
    var_dict = json.loads(qactual.var_dict)

    correct = insert_evaluate_variables(to_eval, var_dict)
    return compare_numeric_with_precision(correct, given, precision, p_type)


def grade_long(qactual):
    """
    Grades long answer questions.
    """
    return None


def string_match(correct, given, qactual=None):
    """
    Returns whether the ``given`` string matches the ``correct`` string

    Ignores capitalization and hyphens
    """
    if isinstance(correct, basestring):
        correct = [correct, ]

    for item in correct:
        item = item.strip()
        given = given.strip()
        if item.lower() == given.lower():
            return True

        given.replace('-', ' ')
        if item.lower() == given.lower():
            return True

        # Wait, it might be a quick_eval string:
        # Make sure the original case is used here, not lower case.
        out = deal_with_quick_eval(item, given, qactual)
        if out:
            return out
        else:
            print('Given: [%s] to match with %s' % (given, str(item)))
            return out

    print('Given: [%s] to match with %s' % (given, str(correct)))
    return False


def compare_numeric_with_precision(correct, given):
    """
    Compares precision of a ``given`` string to the ``correct`` item, to
    a given level of ``precision``.

    ``correct`` is a list made of 3 parts [value, precision, p_type]

    The precision type, ``p_type`` is either ``rel`` or ``abs``:

    A ``rel``: correct if within +/- correct value * precision
        e.g. correct value = 56.2 and precision is 1E-2
             The answer is correct if within 56.2 +/- (56.2*1E-2)
                                 i.e. within 56.2 +/- 0.562
                                 i.e. within [55.638 to 56.762]

    B ``abs``: correct within an absolute bound.
        e.g. correct value is 71.34 and if precision is 1E-2
             The answer is correct if within 71.34 +/- 0.01
                                 i.e. within 71.33 or 71.35


    Returns one of the following:
    * True      (it matches, to within the level of precision)
    * False     (the answer is incorrect)
    * 'Too many significant figures'
    * 'Could not convert answer to a numeric result'

    For example, let the correct value be 67.1, with precision = 0.3, and
    ``abs`` precision. The ``correct`` = [67.1, 0.3, 'abs']:

    * if ``given`` is 67.14414,    then return (True, 'SigFigs')
    * if ``given`` is 62.2515677,  then return (False, 'Wrong value')
    * if ``given`` is 67.2,        then return (True, None)
    * if ``given`` is 34.21768363, then return (False, 'SigFigs')
    """

    correct_v, precision, p_type = correct
    correct_v = str(correct_v)
    precision = str(precision)
    from decimal import Decimal, InvalidOperation
    correct_d = Decimal(correct_v)

    if p_type in ('rel', 'relative'):
        delta = correct_d * Decimal(precision)
    else:
        delta = Decimal(precision)

    lower_b, upper_b = correct_d - delta, correct_d + delta

    try:
        given_d = Decimal(given)
    except InvalidOperation:
        return 'Could not convert answer to a numeric result'
    if given_d < lower_b or given_d > upper_b:
        return (False, 'Wrong value')

    # Test significant figures
    correct_d_sigfigs = correct_d.quantize(given_d)
    if correct_d_sigfigs.compare_total(correct_d) == Decimal('0'):
        return (True, None)
    else:
        return (True, 'SigFigs')
