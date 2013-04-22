#import re
#import csv
try:
    import simplejson as json
except ImportError:
    import json
#import random
#import logging
#import hashlib
#from collections import defaultdict

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

            if qactual.qtemplate.q_type in ('tf', 'mcq', 'multi',):
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
    negative_grading_multi = True
    negative_deduction_multi = 0.5

    #
    answer = qactual.given_answer
    grading = json.loads(qactual.qtemplate.t_grading)

    grade_value = 0.0
    if qactual.given_answer == '':
        grade_value = 0.0

    elif qactual.qtemplate.q_type in ('tf', 'mcq',):
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
            elif negative_grading_multi:
                grade_value -= negative_deduction_multi


    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value)

    return grade


def grade_short(qactual):
    """
    Grades short answer questions.
    """
    #compare qactual.given_answer to qactual.grading_answer
    #``grading_answer`` doesn't exist for the earlier quests.
    grading = json.loads(qactual.qtemplate.t_grading)
    keys = [item[0] for item in grading.items()]
    grading[keys[0]]

    from question.templatetags.quest_render_tags import EvaluateString
    a = EvaluateString(format_string=)



    grade_per_key = qactual.qtemplate.max_grade
    grade_value = 0.0
    grade = Grade.objects.create(graded_by=get_auto_grader(),
                                 approved=True,
                                 grade_value=grade_value)

    return grade


def grade_long(qactual):
    """
    Grades long answer questions.
    """
    return None