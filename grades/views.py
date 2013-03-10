#import re
#import csv
#try:
    #import simplejson as json
#except ImportError:
    #import json
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
    #quests = QActual.objects.filter(


    return HttpResponse('All graded')
