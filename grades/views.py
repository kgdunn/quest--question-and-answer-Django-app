import re
try:
    import simplejson as json
except ImportError:
    import json

import logging
logger = logging.getLogger('quest')

#from django.conf import settings
from django.core.context_processors import csrf
#from django.core.exceptions import ValidationError
#from django.template import Context, Template, Library
from django.contrib.auth.decorators import login_required
from django.core.context_processors import csrf
from django.shortcuts import (HttpResponse, render_to_response,
                              RequestContext)


# 3rd party imports
import numpy as np

# Our imports
from question.models import (QTemplate, QActual, Inclusion, QSet)
from question.views import validate_user
from person.models import UserProfile
from grades.models import Grade
from utils import insert_evaluate_variables, send_email
from course.models import Course

reason_codes = {'SigFigs': 'Too many significant figures',
                'Negative MCQ': 'Lost grades for checking incorrect entries',
                'Not answered': 'Question was not answered',
                'Wrong value': 'Wrong answer given',
                'No match': 'Answer could not be matched with the template',
                'Blank answer': 'Blank answer',
                'Not convertable': 'Answer could not converted to a numeric result'}

negative_deduction_multi = 0.5
negative_sigfigs = 0.25


def get_auto_grader():
    """ Get the UserProfile for the ``auto-grader''
    """
    return UserProfile.objects.filter(role='Grader',
                                      slug='quest-grader-previewer')[0]


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

    count = 0
    for student in students:
        for qactual in qset_questions.filter(user=student).order_by('id'):
            if qactual.grade:
                # Do not re-grade a question that has already received a grade
                continue
            else:
                do_grading()
            count += 1

    return HttpResponse('Graded %d questions' % count)


def do_grading(qactual):
    """
    Performs the grading of a question (QActual) for a single student.
    """
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

    elif qactual.qtemplate.q_type in ('peer-eval',):
        grade = grade_peereval(qactual)

    else:
        # TODO(KGD): else, raise an error: unspecified question type
        assert(False)

    # Save the grade
    qactual.grade = grade
    qactual.save()
    return grade  # used by outside functions that only care for the grade


def grade_MCQ(qactual):
    """
    Grades multiple choice questions.
    """
    reason = []

    answer = json.loads(qactual.given_answer) # assume it is always a dict
    grading = json.loads(qactual.qtemplate.t_grading)

    grade_value = 0.0

    if qactual.qtemplate.q_type in ('tf', 'mcq',):
        user_answer = answer.values()
        grade_value = 0.0
        if user_answer:
            # Either the person gets the answer right, or wrong.
            if grading[user_answer[0]][0] == 'key':
                grade_value = qactual.qtemplate.max_grade

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

    reason = list(set(reason)) # remove duplicates
    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value,
                                 reason_description = reason,
                                 )

    return grade


def grade_short(qactual, force_reload=False):
    """
    Grades short answer questions.
    """
    grade_value = 0.0
    token_dict = json.loads(qactual.given_answer)

    if not qactual.grading_answer or force_reload:
        #``grading_answer`` doesn't exist for the earlier quests.
        # this causes some unusual code here

        assert(False) # we shouldn't need this branch anymore as of rev 157.
                       # kept for legacy purposes only.

        #grading = json.loads(qactual.qtemplate.t_grading)
        #TOKEN = re.compile(r'\{\[(.*?)\]\}')
        #INPUT_RE = re.compile(r'\<input(.*?)name="(.*?)"(.*?)\</input\>')
        #html_iter = INPUT_RE.finditer(qactual.as_displayed)

        #grading_answer = dict()
        #for token in TOKEN.finditer(qactual.qtemplate.t_question):
            #link = html_iter.next().group(2)
            #html_key = token.group(1)
            #grading_answer[link] = grading[html_key]

        ## Store this as the grading answer
        #qactual.grading_answer = json.dumps(grading_answer)

    # Main idea: compare qactual.given_answer to qactual.grading_answer
    if qactual.grading_answer:
        grading = json.loads(qactual.grading_answer)
        keys = [item[0] for item in grading.items()]
        grade_per_key = qactual.qtemplate.max_grade / (len(keys) + 0.0)

        reason = []


        for key, value in grading.iteritems():
            string_answer = False
            if token_dict.has_key(key):

                # TODO(KGD): remove this, after quest 8, 9 and 10 are graded
                if isinstance(value, list) and len(value) == 1 and isinstance(value[0], basestring):
                    try:
                        value = eval(value[0])
                    except NameError:
                        if ',' in value[0]:
                            value = value[0].split(',')
                    except:
                        value = deal_with_quick_eval(value[0], qactual)

                if isinstance(value, list) and len(value) == 3 and not\
                        all([isinstance(i, basestring) for i in value]):
                    correct = value
                elif isinstance(value, int):
                    # TODO(KGD): Very unusual: don't allow this in the future
                    correct = [value, 0, 'abs']
                elif isinstance(value, list) and \
                        all([isinstance(i, basestring) for i in value]):

                    string_answer = True

                elif isinstance(value[0], basestring):
                    try:
                        correct = json.loads(value[0].replace("'", '"'))
                    except json.decoder.JSONDecodeError:
                        # Happens, for example, if: u'[+1, 1E-1, "rel"]'
                        # the "+1" does not happily get decoded.
                        correct = eval(value[0].replace("'", '"'))
                else:
                    assert(False)

                if string_answer:
                    out = string_match(value, token_dict[key], qactual)
                else:
                    out = compare_numeric_with_precision(correct,
                                                         token_dict[key])

            else:
                out = (False, 'Not answered')

            if out[0]:
                grade_value += grade_per_key
            else:
                reason.append(reason_codes[out[1]])

            if out[1] == 'SigFigs':
                grade_value -= negative_sigfigs
                reason.append(reason_codes['SigFigs'])

        reason = list(set(reason)) # remove duplicates
        grade = Grade.objects.create(graded_by=get_auto_grader(),
                                     approved=True,
                                     grade_value=grade_value,
                                     reason_description=reason)


    return grade


def grade_long(qactual):
    """
    Grades long answer questions.
    """
    # TODO(KGD): short-term hack to get grading completed
    if len(qactual.given_answer) < 100:
        grade_value = 0.0
    else:
        grade_value = 5.0
    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value,
                                 )
    return grade


def string_match(correct, given, multiple_tries=True):
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
            return (True, None)

        if multiple_tries:
            # Try once more.
            given = handle_special_cases(given).replace('-', ' ')
            return string_match(item, given, multiple_tries=False)

    return (False, 'No match')


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

    # Handle the case of negative ``correct_d`` values properly, using abs()
    lower_b, upper_b = correct_d - abs(delta), correct_d + abs(delta)

    try:
        given_d = Decimal(given)
    except InvalidOperation:
        if given:
            # A few last tries for corner cases:
            try:
                given_d = Decimal(handle_special_cases(given))
            except InvalidOperation:
                return (False, 'Not convertable')
        else:
            return (False, 'Blank answer')

    # These must be inequalities (do not use <= or >=)
    if given_d < lower_b or given_d > upper_b:
        return (False, 'Wrong value')

    # Test significant figures
    #correct_d_sigfigs = correct_d.quantize(given_d)
    #if correct_d_sigfigs.compare_total(correct_d) >= Decimal('0'):


    # TODO(KGD): deal with significant figures. Ignoring it for now.
    return (True, None)


def handle_special_cases(given):
    """
    Handles some interesting corner cases that have been observed:

    \u2212 = "-" (a hyphen, instead of a minus sign)
    """
    if u'\u2212' in given:
        given = given.replace(u'\u2212', '-')

    return given


def deal_with_quick_eval(eval_str, qactual):
    """
    Given the quick_eval answer, and the given answer, makes a judgement on it,
    i.e. returns True or False if it matches to the required degree of
    significance.

    e.g. string: '[{% quick_eval "20/2.053749" 3 %},1e-2,\'rel\']'
         given:  9.76'

    """
    TAG_RE = re.compile(r'^(.*?){%(.*?)%},(.*?),(.*?)](.*?)$')
    to_eval = '{%' + TAG_RE.search(eval_str).group(2) + '%}'
    precision = TAG_RE.search(eval_str).group(3)
    p_type = TAG_RE.search(eval_str).group(4).strip('"').strip("'")
    var_dict = json.loads(qactual.var_dict.replace("'", '"').replace('""', '"'))
    correct = insert_evaluate_variables(to_eval, var_dict)
    return [float(correct), float(precision), p_type]


@login_required
def grade_summary(request, course_code_slug):
    results = dict()
    students = UserProfile.objects.filter(courses__slug=course_code_slug)
    for student in students:
        qset_grade = []
        qset_maxes = []
        for qset in QSet.objects.filter(course__slug=course_code_slug):
            max_grade = 0.0
            actual_grade = 0.0
            for qa in QActual.objects.filter(qset=qset).filter(user=student):

                max_grade += qa.qtemplate.max_grade
                if qa.grade:
                    actual_grade += qa.grade.grade_value
                else:
                    max_grade = np.NaN

            qset_grade.append(actual_grade)
            qset_maxes.append(max_grade)


        # All done with this student
        qset_grade.reverse()
        qset_maxes.reverse()
        email = student.user.email
        prefix = email[0:email.find('@')]
        results[prefix] = np.round(np.array(qset_grade) \
                                              / np.array(qset_maxes) * 100, 1)

    out = []
    for key, value in results.iteritems():

        value = str(['%5.1f'%i for i in value])
        out.append('%50s, %s|' % (key, value[1:-1]))

    return HttpResponse('\n'.join(out))


def fix_glitch(request):

    course_code_slug = 'statistics-for-engineering-6c3'
    question_set_slug = 'week-3'
    # Iterate through all questions by all students in the QSet
    students = UserProfile.objects.filter(courses__slug=course_code_slug)
    qset_questions = QActual.objects.filter(qset__slug=question_set_slug)


    for student in students:
        for qactual in qset_questions.filter(user=student).order_by('id'):

            if qactual.given_answer == '':
                pass

            elif qactual.qtemplate.q_type in ('short'):
                grade = grade_short(qactual, force_reload=True)
                if qactual.grade:
                    if grade.grade_value != qactual.grade.grade_value:
                        print('Changed [%s]:(%s) -> (%s)' %
                              (qactual.user.slug,
                                  qactual.grade.grade_value, grade.grade_value))
                    #qactual.grade.delete()
                    qactual.grade = grade
                    qactual.save()
                else:
                    assert(False)


def get_peer_comments(user, qactuals, username):
    """
    From a QuerySet of ``qactuals`` return the comments from the ``user``'s
    peers.
    """
    NAME = re.compile(r'strong\>(.*?)\</strong\>')
    out = []
    for other in user.get_peers():
        qa = qactuals.filter(user__slug=other[1])[0]
        if qa.grading_answer != '':
            # Old version of peer-eval: create the grading answer
            ans = {}
            try:
                ga = json.loads(qa.given_answer)
            except json.decoder.JSONDecodeError:
                continue
            for item, value in ga.iteritems():
                if item.startswith('pf__'):
                    ans[item] = [int(value),]
                    continue

                idx = qa.as_displayed.find(item)
                string = qa.as_displayed[idx-250:idx]
                if 'constructive' in string:
                    ans[item] = (NAME.search(string).group(1), 'Constructive',
                                 ga[item])
                elif 'appreciated' in string:
                    ans[item] = (NAME.search(string).group(1), 'Appreciated',
                                 ga[item])

            # Store the answer
            qa.grading_answer = json.dumps(ans)
            qa.save()
        else:
            pass # already processed their QActual

    # Repeat again, this time getting the actual responses
    merged = ''
    for other in user.get_peers():
        qa = qactuals.filter(user__slug=other[1])[0]
        try:
            gr_ans = json.loads(qa.grading_answer)
        except json.decoder.JSONDecodeError:
            gr_ans = {}

        if qa.given_answer:
            out.append([other[0], '', None])
            for key, val in gr_ans.iteritems():
                if isinstance(val[0], basestring) and val[0] == username:
                    out[-1][1] += "%s: %s\n" % (val[1], val[2])
                    merged += "%s: %s\n" % (val[1], val[2])
                if isinstance(val[0], int) and user.slug.replace('-','_')\
                                                        in key:
                    out[-1][2] = val[0]

        else:
            out.append([other[0], '--No comment--', 0])


    out.append(['Merged', merged, -99.9])

    return out

@login_required
def grade_peer_eval(request):            # URL: ``admin-grade-peer-eval``
    """
    Grade the peer evaluations
    """
    if request.method == 'GET':
        ctxdict = { 'item_list': QSet.objects.all(),
                    'item_type': 'qset_slug'
                  }
        ctxdict.update(csrf(request))
        return render_to_response('grades/select-peer-evaluation.html', ctxdict,
                                    context_instance=RequestContext(request))

    elif request.method == 'POST' and \
                                      request.POST['item_type'] == 'qset_slug':
        qset_slug = request.POST.get('item_slug', '')
        qset = QSet.objects.filter(slug=qset_slug)[0]
        qtemplates = QTemplate.objects.filter(qset=qset).filter(q_type='peer-eval')
        if len(qtemplates) == 0:
            return HttpResponse(('There are no peer evaluations in the '
                                  'selected question set'))
        else:
            ctxdict = { 'item_list': qtemplates,
                        'item_type': 'qtemplate_slug'
                    }
            ctxdict.update(csrf(request))
            return render_to_response('grades/select-peer-evaluation.html',
                                      ctxdict,
                                      context_instance=RequestContext(request))

        qactuals = QActual.objects.filter(qset=qset)

    elif request.method == 'POST' and \
                               request.POST['item_type'] == 'qtemplate_slug':
        qtemplate_slug = request.POST.get('item_slug', '')
        qtemplate = QTemplate.objects.filter(slug=qtemplate_slug)[0]
        qactuals = QActual.objects.filter(qtemplate=qtemplate)

        users = []
        for item in qactuals:
            username = '%s %s' % (item.user.user.first_name,
                                  item.user.user.last_name)

            users.append((username, get_peer_comments(item.user, qactuals,
                                                    username), item.user.slug))

        ctxdict = {'users':  users,
                   'qset_slug': item.qset.slug}
        ctxdict.update(csrf(request))
        return render_to_response('grades/grade-peer-evaluation.html', ctxdict,
                                  context_instance=RequestContext(request))

@login_required
def email_user_feedback(request):        # URL: ``admin-email-user-feedback``
    """
    """
    if request.method != 'POST':
        return HttpResponse('Bad input')


    userP = UserProfile.objects.filter(slug=request.POST['user'])[0]
    to_address = userP.user.email
    qset = QSet.objects.filter(slug=request.POST['qset_slug'])[0]
    message = """\
%s,

This message is regarding peer feed for Quest "%s", in course %s.

These comments were left by your team members. They are in random order.
Not all comments are necessarily constructive, so consider this as advice
and opinion.

---
%s
---

Sent from the http://quest.mcmaster.ca web server.
    """ % (userP.user.first_name, qset.name, qset.course.name,
           request.POST['comments'])

    subject = 'Peer feedback from Quest: %s' % qset.name

    out = send_email([to_address, ], subject, message)
    logger.info('Send email to "%s" about %s: %s' % (to_address,
                                                     qset.name,
                                                     request.POST['comments']))
    if out:
        logger.debug('Successfully sent peer feedback to %s' % to_address)
    else:
        logger.error('Unable to send submission confirmation email to: %s' %
                    to_address)

    return HttpResponse('Sent email')
