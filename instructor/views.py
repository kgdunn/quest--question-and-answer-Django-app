# Python and Django imports
import re
import csv
try:
    import simplejson as json
except ImportError:
    import json

import random
import logging
import hashlib
import datetime
from collections import defaultdict

from django.conf import settings
from django.core.context_processors import csrf
from django.core.exceptions import ValidationError
from django.template import Library
from django.contrib.auth.decorators import login_required
from django.shortcuts import (HttpResponse, render_to_response,
                              RequestContext)
register = Library()

# 3rd party imports
import markdown
import numpy as np

# Our imports
from question.models import (QTemplate, QActual, Inclusion, QSet)
from question.views import validate_user, get_questions_for_user
from person.models import (UserProfile, User, Group)
from person.views import create_sign_in_email
from tagging.views import get_and_create_tags
from utils import (generate_random_token, send_email,
                   insert_evaluate_variables, unique_slugify)
from course.models import Course
from grades.views import do_grading

logger = logging.getLogger('quest')

class BadVariableSpecification(Exception): pass

# TODO(KGD): allow these to be case-insenstive later on
CONTRIB_RE = re.compile(r'^Contributor:(\s*)(.*)$')
TAGS_RE = re.compile(r'^Tags:(\s*)(.*)$')
DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(.*)$')
GRADES_RE = re.compile(r'^Grade:(\s*)(.*)$')
FEEDBACK_RE = re.compile(r'^Feedback:(\s*)(.*)$')
NAME_RE = re.compile(r'^Name:(\s*)(.*)$')

LURE_RE = re.compile(r'^\&(\s*)(.*)$')       # & lure answer
KEY_RE = re.compile(r'^\^(\s*)(.*)$')        # ^ correct answer
FINALLURE_RE = re.compile(r'^\%(\s*)(.*)$')  # % final MCQ option, but a lure
FINALKEY_RE = re.compile(r'^\%\^(\s*)(.*)$')   # %^ final MCQ option, correct

GRADE_SHORT_RE = re.compile(r'(?P<key>.*?):(?P<value>.*)')

class ParseError(Exception):
    pass


def get_type(mcq_dict, keytype):
    """Gets the required ``keytype`` from the MCQ grading dictionary.
    The ``keytype`` returned only needs to startswith ``keytype``.
    That we ensure "final-lure" and "final-key" are still returned when
    requesting "final"
    """
    for key, value in mcq_dict.iteritems():
        if value[0].startswith(keytype):
            yield value[1], key


def split_sections(text):                                          # helper
    """
    Splits the problem statement into its sections. Section are denoted by
    double brackets:
        [[section name]]
        section content
        [[next section]]
        more content
        goes here

    will return
    {'section name': ['section content', ], 'next section', ['more content',
     'goes here']
    }
    """
    SECTION_RE = re.compile(r'(\s*)\[\[(\S*)\]\](\s*)')
    out = {}
    content = []
    for line in text:
        if SECTION_RE.match(line):
            section = SECTION_RE.match(line).group(2).lower()
            content = []
            out[section] = content
        else:
            content.append(line)

    return out


def parse_MCQ_TF_Multi(text, q_type):                             # helper
    """
    Multiple choice (MCQ)
    True/False (TF)
    Multiple checkbox answer (Multi)

    are parsed and processed here.
    """
    instructions = []
    while text[0].strip() != '--':
        instructions.append(text[0].strip())
        text.pop(0)
    text.pop(0)
    t_question = '\n'.join(instructions)

    # Handles the case of the """--\n--\n""" where we specify the solution in
    # terms of a function.
    if text[0].strip() == '--':
        t_solution = ''
        t_grading = '<function>'
        # TODO(KGD): complete this still
    else:
        t_grading = dict()

        start_letter = 'a'
        for line in text:
            start_letter = chr(ord(start_letter) + 1)

            if len(line.strip()) == 0:
                continue

            # This check must be before the next one
            elif line.startswith('%^'):
                section_name = start_letter + generate_random_token(4)
                t_grading[section_name] = ['final-key', ]
                final = FINALKEY_RE.match(line).group(2)
                t_grading[section_name].append(final)
                continue

            elif line.startswith('%'):
                section_name = start_letter + generate_random_token(4)
                t_grading[section_name] = ['final-lure', ]
                final = FINALLURE_RE.match(line).group(2)
                t_grading[section_name].append(final)
                continue

            elif line.startswith('^'):
                section_name = start_letter + generate_random_token(4)
                t_grading[section_name] = ['key', ]
                key = KEY_RE.match(line).group(2)
                t_grading[section_name].append(key)
                continue

            elif line.startswith('&'):
                section_name = start_letter + generate_random_token(4)
                t_grading[section_name] = ['lure', ]
                lure = LURE_RE.match(line).group(2)
                t_grading[section_name].append(lure)
                continue

            t_grading[section_name][1] += '\n' + line


    # Do a sanity check: MCQ and TF must have a single correct answer
    #                    MULTI must have more than one correct answer<-NO
    if q_type in ('tf', 'mcq'):
        found_one = False
        for key, value in t_grading.iteritems():
            if value[0] in ('final-key', 'key'):
                if found_one:
                    raise ParseError(('Only one option can be correct in an '
                                      'MCQ or TF question. Maybe you intended '
                                      'a MULTI answer question?'))
                else:
                    found_one = True

    # Maybe the instructor wants to "trick" the user and there is only
    # one valid option

    #if q_type in ('multi',):
        ## None [0] -> False [1 correct answer] -> True [2 or more correct]
        #found_many = None
        #for key, value in t_grading.iteritems():
            #if value[0] in ('final-key', 'key'):
                #if found_many is None:
                    #found_many = False
                #elif found_many is False:
                    #found_many = True

        #if found_many is not True:
            #raise ParseError(('Multi-answer checkbox questions require two '
                              #'or more correct answers'))


    # Cleaning: for T/F question, strip away newlines, leaving only 1 answer
    if q_type == 'tf':
        for key, value in t_grading.iteritems():
            value[1] = value[1].strip()
            t_grading[key] = value

    # Generate the solution string for MCQ/TF/MULTI questions
    if q_type in ('mcq', 'tf', 'multi'):
        soln_str = 'The solution is: "%s"'
        if q_type in ('mcq', 'tf'):
            try:
                key, _ = get_type(t_grading, keytype='key').next()
            except StopIteration:
                key, _ = get_type(t_grading, keytype='final-key').next()
            t_solution = soln_str % key

        if q_type in ('multi',):
            soln_str = []
            final_soln = ''
            solutions = t_grading.values()
            solutions.sort()
            if solutions[0][0] == 'final-key':
                final_soln = solutions.pop(0)
            for item in solutions:
                if item[0] == 'key':
                    soln_str.append('*\t%s' % item[1])

            if final_soln:
                soln_str.append('*\t%s' % final_soln[1])

            if len(soln_str) > 1:
                soln_str.insert(0, 'The correct answers are: ')
            elif len(soln_str) == 1:
                soln_str.insert(0, 'The correct answer is: ')

            soln_str.insert(1, '')

            t_solution = '\n'.join(soln_str)

    return t_question, t_solution, t_grading


def parse_OTHER(text, solution, grading, q_type):                  # helper
    """
    Short and long answer questions are parsed and processed here.
    The solution test and grading text are also checked and returned.

    A short answer region is given by {[var_short]} these brackets.
    A long answer region is indicated by {[[var_long]]} these brackets.

    Multiple instances of such brackets may appear within the question. The
    grading for the question must supply answers for the brackets, in the same
    order. For example, the [[grading]] portion of the template could be:

    [[grading]]
    {var_short}: bar
    {var_short}: BAR     <-- multiple answers can be given,
    {var_long}: Grading text can be provided for long answer questions,
    but will never be used
    """
    if q_type in ('short', 'long'):#, 'multipart'):
        # The space is the list join() is intentional; to ensure imported text
        # that spans lines gets correctly spaced; double spaces are handled
        # well in HTML anyway, so 2 spaces won't show up badly.
        # Strip off trailing and starting newlines and blank spaces
        t_question = u' \n'.join(text).strip('\n ')
        t_solution = u' \n'.join(solution).strip('\n ')
        t_grading = u' \n'.join(grading).strip('\n ')

    if q_type == 'short':
        t_grading_orig, t_grading = t_grading, defaultdict(list) # Love Python
        for line in t_grading_orig.split('\n'):
            if GRADE_SHORT_RE.match(line):
                key, val = GRADE_SHORT_RE.match(line).groups()
                t_grading[key].append(val.strip())

    return t_question, t_solution, t_grading


def parse_question_text(text):                                    # helper
    """
    Parses a question's template text to create our internal question
    representation. For example, for a multiple choice question:


    [[type]]
    mcq

    [[attribs]]
    Name: Multiplication warm-up
    Contributor: Kevin Dunn
    Difficulty: 2
    Tags: multiplication, math
    Grade: 3

    [[question]]
    If a=1, b=2. What is a*b?
    --
    [[grading]]
    & 12    <-- distractors (lures) begin with "&"
    & 1     <-- distractor
    ^2      <-- correct answer(s) begin with "^"
    & 4     <-- distractor
    % None  <-- option that's presented last (but is wrong) begins with "%"

    %^ 2    <-- use this if you want the correct answer presented last
                usually used when "All of the above" or "None of the above"
                is the correct answer.
    [[variables]]
    [[solution]]
    From multiplication rules we have that a*b = 2.
    """
    t_question = t_solution = t_grading = var_dict = t_code = ''
    # Force it into a list of strings.
    if isinstance(text, basestring):
        if text.count('\n') == text.count('\r'):
            text = text.split('\r\n')
        elif text.count('\n') and text.count('\r') == 0:
            text = text.split('\n')
        else:
            # Shouldn't have to execute this, but rather
            text = text.replace('\r', '').split('\n')

    # ``sd`` = section dictionary; see comments for function below.
    sd = split_sections(text)

    # These items are mandatory
    if not sd.has_key('type'):
        raise ParseError('[[type]] section not given')
    if not sd.has_key('question'):
        raise ParseError('[[question]] section not given')

    if isinstance(sd['type'], list):
        sd['q_type'] = ''.join(sd.pop('type')).strip().lower()
    elif isinstance(sd['type'], basestring):
        sd['q_type'] = sd.pop('type').strip().lower()

    if sd['q_type'] in ('tf', 'mcq', 'multi'):
        t_question, t_solution, t_grading = parse_MCQ_TF_Multi(sd['question'],
                                                               sd['q_type'])
        if sd.has_key('solution'):
            t_solution += '\n\n' + '\n'.join(sd['solution'])

        sd.pop('question')

    if sd['q_type'] in ('peer-eval',):
        t_question = '\n'.join(sd['question'])
        sd.pop('question')

    if sd['q_type'] in ('short', 'long'): #, 'multipart'):
        if not sd.has_key('solution'):
            raise ParseError(('[[solution]] section not given for %s question'
                              ' [%s...]') % (sd['q_type'],
                                            str(sd['question'])[0:30]))
        if not sd.has_key('grading'):
            raise ParseError(('[[grading]] section not given for %s question'
                              ' [%s...]. Required to assist person grading') %\
                            (sd['q_type'], str(sd['question'])[0:30]))

        # This function really doesn't do anything. Placeholder for now
        # Remember that ``parse_question_text()`` is intended only to load
        # text templates into our internal representation. Text templates
        # match our internal representation closely anyway.
        # We render the question and solution later.
        t_question, t_solution, t_grading = parse_OTHER(sd['question'],
                                                        sd['solution'],
                                                        sd['grading'],
                                                        sd['q_type'])

    # If there's source code:
    if 'code' in sd.keys():
        sd['t_code'] = '\n'.join(sd['code'])
        # TODO(KGD): check the first line starts with '#! ......'
    else:
        sd['t_code'] = t_code


    sd['contributor'] = 1
    sd['tags'] = ''
    sd['difficulty'] = 1
    sd['max_grade'] = 1
    sd['enable_feedback'] = True
    if sd.has_key('attribs'):
        lines = sd['attribs']
        for line in lines:
            line = line.strip()

            if CONTRIB_RE.match(line):
                sd['contributor'] = CONTRIB_RE.match(line).group(2).strip()

            if TAGS_RE.match(line):
                sd['tags'] = TAGS_RE.match(line).group(2)

            if DIFFICULTY_RE.match(line):
                sd['difficulty'] = DIFFICULTY_RE.match(line).group(2)

            if GRADES_RE.match(line):
                sd['max_grade'] = GRADES_RE.match(line).group(2)

            if NAME_RE.match(line):
                sd['name'] = NAME_RE.match(line).group(2)

            if FEEDBACK_RE.match(line):
                sd['enable_feedback'] = FEEDBACK_RE.match(line).group(2)\
                                                        .lower() == 'true'

        # Remove this key: not required anymore
        sd.pop('attribs')

    # Process the variables:
    var_dict = {}
    if sd.get('variables', ''):
        var_re = re.compile(r'(\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*):(.*)')
        for line in sd['variables']:
            if var_re.match(line):
                _, key, _, val = var_re.match(line).groups()
                key = key.strip()
                # Strip away the brackets and split the string apart at the
                # commas; store as a list
                val = val.strip()

                # Likely is a ``choices`` tag, as in
                # variable:{'choices': ['Opt1', 'Opt2', 'Opt3']}

                if val.startswith('{'):
                    val = val.replace("'", '"')
                    try:
                        choice_dict = json.loads(val)
                    except ValueError, e:
                        raise BadVariableSpecification('Could not decode: %s'%
                                                       line)

                    if len(choice_dict) != 1 and \
                                        choice_dict.keys()!=['choices']:
                        raise BadVariableSpecification("""A "choices" \
variable  must be specified as "{'choices': ['option a', 'option b', 'etc']}"\
""")
                    var_dict[key] = [choice_dict, None]
                    continue

                val = [item.strip() for item in val.strip('[]').split(',')]
                if len(val) in (3, 4, 5):
                    for idx, entry in enumerate(val[0:3]):
                        val[idx] = np.float(entry)
                else:
                    raise BadVariableSpecification(('Variable spec list '
                                                    'should be 3, 4, or 5'
                                                    'entries in length.'))
                var_dict[key] = val
            else:
                # TODO(KGD?): silently fail on variable lines that don't match
                if line.strip() != '':
                    raise BadVariableSpecification('Could not decode: %s' %\
                                                    line)

        sd.pop('variables')


    # Final checks before returning
    if not sd.has_key('name'):
        summary = t_question.replace('\n','').strip()
        sd['name'] = summary[0:min(250,len(summary))]

    sd['t_question'] = t_question
    sd['t_solution'] = t_solution
    sd['t_grading'] = t_grading
    sd['t_variables'] = var_dict


    return sd


def create_question_template(text, user=None):
    """
    Creates the QTemplate (question template) and adds it to the database.

    Assumes the ``text`` is well-formatted. This should be checked external
    to this function. (e.g. it has all the necessary parts for a complete
    question)
    """

#YOu've changed something here, so that strings are now converted to double
#strings, and not the dict. For t_grading

    sd = parse_question_text(text)
    contributor = user

    # Maybe we've imported this template before. Update the previous ones.
    exist = QTemplate.objects.filter(name=sd['name'],
                                     contributor=contributor,
                                     difficulty=sd['difficulty'],
                                     max_grade = sd['max_grade'],
                                     enable_feedback = sd['enable_feedback'],
                                     t_question = sd['t_question'],
                                     t_solution = sd['t_solution'],
                                     t_variables = sd['t_variables'])
    if exist:

        # DO NOT EVER OVERWRITE AN EXISTING QTEMPLATE.
        # It will break the grading for questions that are in progress, but
        # not graded yet.
        logger.warn(('Found an existing question with the same/similar '
                     'template. Skipping it: [%s]') % sd['name'])

        # Return only the first instance of the template (there should only
        # be one anyway)
        return exist[0]

    # If it doesn't exist, create it, but use fake objects for testing and
    # for previews. Only write actual templates to the database
    if user is None:
        class Fake_Template(object):
            def __init__(self, initial_data):
                for key in initial_data:
                    setattr(self, key, initial_data[key])

        qtemplate = Fake_Template(sd)
    else:
        qtemplate = QTemplate.objects.create(name=sd['name'],
                        q_type=sd['q_type'],
                        contributor=contributor,
                        difficulty=sd['difficulty'],
                        max_grade = sd['max_grade'],
                        enable_feedback = sd['enable_feedback'],
                        t_question = sd['t_question'],
                        t_solution = sd['t_solution'],
                        t_grading = sd['t_grading'],
                        t_variables = sd['t_variables'],
                        t_code = sd['t_code'])

        for tag in get_and_create_tags(sd['tags']):
            qtemplate.tags.add(tag)

    return qtemplate


def choose_random_questions(qset, user):
    """
    Returns a list of QTemplates, ``qts``, where the questions in that list
    were randomly selected according to rules defined by the ``qset`` object.

    Also ensures the questions chosen haven't been previously seen by the user.
    """
    r_tries = 20

    # Retrieve all previous questions attempted by the user and remove
    # these from consideration.


    # Add mandatory questions to the list
    mandatory = qset.inclusion_set.all()
    all_id = range(len(mandatory))

    #for attempt in range(r_tries):

    N_quest = np.random.random_integers(qset.min_num, qset.max_num)
    random.shuffle(all_id)
    qts = [mandatory[idx] for idx in all_id[0:N_quest]]


    # Finally, randomize (permute) the list order
    #np.random.shuffle(qts)
    return qts


@login_required                       # URL: ``admin-load-from-template``
def load_from_template(request):
    """
    Given a text file, loads various question templates for a course.

    Each question is split by "#----" in the text file
    """
    if request.POST:
        question_set_slug = request.POST.get('qset_slug')
        course_code_slug = request.POST.get('course_slug')
        course = validate_user(request, course_code_slug, question_set_slug,
                               admin=True)
        questions = request.FILES.get('template_file').read().split('#----')

        if isinstance(course, HttpResponse):
            return course
        if isinstance(course, tuple):
            course, qset = course

        additional = []
        for question in questions:
            if not question.strip():  # avoid empty text
                continue
            template = create_question_template(question,
                                                user=request.user.get_profile())
            included_item = Inclusion(qset=qset, qtemplate=template)
            try:
                included_item.save()
            except ValidationError, e:
                text = ('This template [ID=%d] has already been included in '
                        'this question set [%s]') % (template.id, qset.name)
                logger.warn(text)
                additional.append(text)


        ctxdict = {'output': 'All questions loaded from the template.',
                   'additional': str(['<li> %s'%item for item in additional]),
                   'course_code_slug':  course_code_slug,
                   'question_set_slug': question_set_slug,
                   }
        ctxdict.update(csrf(request))
        return render_to_response('instructor/generate-questions.html',
                                  ctxdict,
                                  context_instance=RequestContext(request))

    else:
        ctxdict = {'course_list': Course.objects.all(),
                   'qset_list': QSet.objects.all().order_by('-ans_time_start'),
                  }
        ctxdict.update(csrf(request))
        return render_to_response('instructor/load-from-template.html',
                                  ctxdict,
                                  context_instance=RequestContext(request))

@login_required                       # URL: ``admin-load-class-list``
def load_class_list(request):
    """
    Load a CSV file class list (exported from Avenue via copy/paste to textfile)
    LASTNAME, FIRSTNAME,email.prefix,0001231  <-- student number
    No header row allowed
    """
    if request.method == 'GET':
        ctxdict = {'course_list': Course.objects.all(),
                   'suffix': '@mcmaster.ca',
                  }
        ctxdict.update(csrf(request))
        return render_to_response('instructor/load-class-list.html', ctxdict,
                                    context_instance=RequestContext(request))

    elif request.method == 'POST':
        course_slug = request.POST.get('course_slug', '')
        course = Course.objects.filter(slug=course_slug)[0]
        email_suffix = request.POST.get('email_suffix', '')

        users_added = []
        rdr = csv.reader(request.FILES['csv_file'], delimiter=',')
        for row in rdr:
            if len(row)==4:
                last, first, email_id, student_id = row
                group = None
            if len(row)==5:
                last, first, email_id, student_id, group = row

                group_obj = Group.objects.filter(name=group)
                if len(group_obj) == 0:
                    group = Group(name=group)
                    group.save()
                else:
                    group = group_obj[0]

            username = '%s-%s' % (first.strip().lower(),
                                  last.strip().lower())

            if len(student_id) == 6:
                student_id = '0' + student_id

            email_id = email_id.strip()
            if '@' not in email_id:
                email = email_id+email_suffix
            else:
                email = email_id


            try:
                # Rather fetch by student number, instead of emails.
                # Emails sometimes have spaces at the start of them.
                #user_obj = UserProfile.objects.get(student_number=student_id)
                #obj = user_obj.user
                #assert(student_id.strip() == obj.get_profile().student_number)

                # Go back to email address, it is more unique
                obj = User.objects.get(email=email)
                #obj = user_obj.get_profile()
                #assert(student_id.strip() == obj.get_profile().student_number)


                logger.info('User [%s] already exists' % email)
            #except UserProfile.DoesNotExist:
            except User.DoesNotExist:
                obj = User(username=username,
                           first_name=first.strip(),
                           last_name=last.strip(),
                           email=email_id+email_suffix)

                unique_slugify(obj, obj.username, 'username')
                obj.save()
                logger.info('Created user for %s with name: %s' % (course_slug,
                                                                   username))
                users_added.append(obj)

            # Add/updated the user's profile
            profile = obj.get_profile()
            profile.role = 'Student'
            profile.group = profile.group or group
            profile.student_number = student_id.strip()
            profile.courses.add(course)
            profile.save()

        # Finally, return when completed

        return HttpResponse(content='Added users<br>%s' % \
                            str(['<li> %s'%item for item in users_added]))

@login_required                       # URL: ``admin-generate-questions``
def generate_questions(request, course_code_slug, question_set_slug):
    """
    1. Generates the questions from the question sets, rendering templates
    2. Emails users in the class the link to sign in and start answering
    """
    course = validate_user(request, course_code_slug, question_set_slug,
                           admin=True)
    if isinstance(course, HttpResponse):
        return course
    if isinstance(course, tuple):
        course, qset = course

    # Now render, for every user, their questions from the question set
    which_users = UserProfile.objects.filter(courses=course)
    user_objs = [userP.user for userP in which_users]
    for user in user_objs:

        if qset.random_choice:
            qts = choose_random_questions(qset, user)
        else:
            qts = qset.include.all().order_by('id')

        question_list = []
        for idx, qt in enumerate(qts):
            # Check if ``QActual`` already exists:
            qa = QActual.objects.filter(qtemplate=qt,
                                        qset=qset,
                                        user=user.get_profile(),
                                        is_submitted=False)
            question_list.extend(qa)
            if len(qa) == 0:
                # This is the usual path through the code; creating a new
                # QActual. We don't even re-create a QActual in the case that
                # the generation step is called a second or subsequent time.

                options = {}
                options['peers'] = user.get_profile().get_peers()
                html_q, html_a, var_dict, grading_answer = render(qt, options)
                qa = QActual.objects.create(qtemplate=qt,
                                            qset=qset,
                                            user=user.get_profile(),
                                            as_displayed=html_q,
                                            html_solution=html_a,
                                            var_dict=var_dict,
                                            grading_answer=grading_answer)
                logger.debug('Create QA with id = %s' % str(qa.id))
                question_list.append(qa)

        question_list = get_questions_for_user(qset, user.get_profile())
        # len(qts) = the number of templates included in the question set, QSet
        # len(question_list) = the number of questions found associated with
        #                      that QSet in the database.
        # There must be a 1:1 correspondence.
        assert(len(question_list) == len(qts))
        n_questions = len(question_list)
        # Run through a 2nd time to add the previous and next links
        for idx, qt in enumerate(question_list):
            prev_q = next_q = None
            if idx == 0:
                if n_questions > 1:
                    next_q = question_list[1]
            elif idx == n_questions-1:
                if n_questions > 1:
                    prev_q = question_list[idx-1]
            else:
                next_q = question_list[idx+1]
                prev_q = question_list[idx-1]

            question_list[idx].next_q = next_q
            question_list[idx].prev_q = prev_q
            question_list[idx].save()


        logger.info('Rendered question set %s (%s) for [%s]' % (qset.slug,
                                                    course.slug,
                                                    user.get_profile().slug))


    to_list = []
    additional = ''
    message_list = []
    out = subject = ''
    for user in user_objs:
        subject, message, to_address = create_sign_in_email(user, qset)
        message_list.append(message)
        to_list.append(to_address)

    if to_list:
        out, to_list_out = send_email(to_list, subject, message_list)

    if out:
        additional = 'Successfully sent multiple emails for sign in to %s' % \
        str(to_list_out)
        logger.debug(additional)
    else:
        additional = 'Unable to send multiple sign-in emails to: %s' % \
                    str(to_list_out)
        logger.error(additional)

    return HttpResponse(('All questions generated for all users for %s'
                          '<p>Additional info: <code>%s</code>') %
                          (qset.slug, additional))

@login_required                       # URL: ``admin-report-responses``
def report_responses(request):
    """
    Reports all the responses from the student for a particular textarea-based
    answer.
    """
    if request.POST:
        qtemplate_slug = request.POST.get('qtemplate_slug')
        course_code_slug = request.POST.get('course_slug')
        qtemplate = QTemplate.objects.get(slug=qtemplate_slug)
        qactuals = QActual.objects.filter(qtemplate__slug=qtemplate_slug)

        out = [qtemplate.t_question, ]
        out.append("""
        <table border="1"><th><tr>
            <td>Q-ID</td>
            <td>Student</td>
            <td>Response</td>
            </tr></th>""")
        for item in qactuals:
            if item.given_answer.strip() == '':
                item.given_answer = '{"_": "NOT ANSWERED"}'

            out.append("""
            <tr><td>{0}</td>
                <td>{1}</td>
                <td>{2}</td>
            </tr>""".format(item.id,
                            item.user.user.email,
                            json.loads(item.given_answer).values()[0]\
                                           .encode('utf8', 'replace')
                            ))

        out.append("</table>")
        return HttpResponse(out)
    else:
        ctxdict = {'course_list': Course.objects.all(),
                   'qtemplate_list': QTemplate.objects.filter(\
                       q_type__iexact='long')
                  }
        ctxdict.update(csrf(request))
        return render_to_response('instructor/report-responses.html',
                                  ctxdict,
                                  context_instance=RequestContext(request))

@login_required                       # URL: ``admin-report-responses-short-answer``
def report_responses_short_answer(request):
    """
    Reports all the responses from the student for a particular short-answer
    answer.
    """
    if request.POST:
        qtemplate_slug = request.POST.get('qtemplate_slug')
        course_code_slug = request.POST.get('course_slug')
        qtemplate = QTemplate.objects.get(slug=qtemplate_slug)
        qactuals = QActual.objects.filter(qtemplate__slug=qtemplate_slug)

        keys = []
        values = []
        t_grading = json.loads(qtemplate.t_grading)
        for key, value in t_grading.iteritems():
            keys.append(key)
            values.append(value[0])

        out = [qtemplate.t_question, ]
        header = """<tr><td>Q-ID</td><td>Student</td>""" + \
            "<td>%s</td>" * len(keys) + "</tr>"
        names = header % tuple(keys)
        expected = header % tuple(values)
        out.append("""<table border="1"><th>""" + names + expected + "</th>")
        for item in qactuals:
            if item.given_answer.strip() == '':
                out.append("""
                <tr><td>{0}</td>
                    <td>{1}</td>
                    <td colspan="{3}">{2}</td>
                </tr>""".format(item.id,
                                item.user.user.email,
                                "Not answered",
                                len(keys)
                                ))
                continue

            # The aim to match the ``item.given_answer`` to be in the same column
            # order as the column headers defined above by ``keys`` and ``values``
            response_code = []
            true_answer = []
            for key, value in json.loads(item.grading_answer).iteritems():
                response_code.append(key)
                true_answer.append(value[0])

            responses = [None, ] * len(keys)
            ga = json.loads(item.given_answer)
            for idx, entry in enumerate(true_answer):
                idx_table = values.index(entry)
                responses[idx_table] = ga[response_code[idx]].encode('utf8', 'replace') or 'NA'


            out.append("""<tr><td>{0}</td> <td>{1}</td>""".format(item.id,
                                                item.user.user.email))

            output =  "<td>%s</td>" * len(keys) + "</tr>"
            out.append(output % (tuple(responses)))


        out.append("</table>")
        return HttpResponse(out)
    else:
        ctxdict = {'course_list': Course.objects.all(),
                   'qtemplate_list': QTemplate.objects.filter(\
                       q_type__iexact='short')
                  }
        ctxdict.update(csrf(request))
        return render_to_response('instructor/report-responses.html',
                                  ctxdict,
                                  context_instance=RequestContext(request))



def evaluate_template_code(code, var_dict):                         #helper
    """
    This function will evaluate any source code included in the template.
    """
    output = ({}, {})
    if not code:
        return output

    # Get the incoming variables
    var_dict_rendered = {}
    for key, values in var_dict.iteritems():
        var_dict_rendered[str(key)] = values[1]

    # Strip out the Language identifier
    lang = code[0:code.find('\n')].strip('#!').strip().lower()
    code = code[code.find('\n'):]

    # Remove any Windows new lines (to be safe, replace them with regular
    # newlines
    code = code.replace('\r', '\n')


    if lang == 'python':
        local_dict = {} #var_dict_rendered
        global_dict = {}
        #code += '\n\n_output_ = quest(locals())'
        try:
            exec(code, None, local_dict)
        except Exception, e:
            logger.error(e)
            raise

        if local_dict.has_key('quest'):
            output = local_dict['quest'](**var_dict_rendered)
        else:
            logger.warn('Python code must contain a "def quest(...)" function')
            output = ({}, {})

    return output


def render(qt, options=None):                                        # helper
    """
    ``options`` is a dict that may be provided, containing keys specific to the
    type of question being rendered. e.g. ``peer-eval`` questions send in the
    names of the user's peers.

    Renders templates to HTML.
    * Handles text
    * MathJax math
    * Pictures/images
    * Calls external code before rendering
    * Generate and return the components used to create a QActual object

    To maintain integrity, rendering from ``QTemplate`` to a ``QActual`` is
    only and ever done ONCE (at rendering time). Later, when the question is
    graded, or reloaded by the user, they will always see the same question.
    This is because questions may contain random values specific to the user
    so they must be rendered only once, including the correct solution, which
    often is dependent on the randomly selected values.

    Rendering order:
        1 Convert our internal representation to HTML
        2 Pick random values for any variables in the question
        3 And/or evaluate any source code to obtain variables and solutions
        4 t_grading['answer'] string is run through rendering as well
        5 Render any variables using our templates.
        6 Convert this markup to HTML.
        7 Create QAactual object and return that

    """
    #---------
    def render_mcq_question(qt):
        """Renders a multiple choice question to HTML."""

        if qt.q_type in ('mcq', 'tf'):
            q_type = 'radio'
        elif qt.q_type in ('multi',):
            q_type = 'checkbox'

        # From: http://www.echoecho.com/htmlforms10.htm
        # The ``name`` setting tells which group of radio buttons the field
        # belongs to. When you select one button, all other buttons in the
        # same group are unselected. Useful when having multiple questions
        # on the page.
        # The ``value`` defines what will be submitted to the server.

        template = ('<label><input type="%s" name="%s" '
                    'value="%s"/>%s</label>')

        lst = []
        name = generate_random_token(8)

        keys =  qt.t_grading.keys()
        keys.sort()

        for key in keys:
            lst.append(template % (q_type, name, key, qt.t_grading[key][1]))



            #for (key, value) in get_type(qt.t_grading, keytype='key'):
                #lst.append(template % (q_type, name, value, key))

            #for (lure, value) in get_type(qt.t_grading, keytype='lure'):
                #lst.append(template % (q_type, name, value, lure))

        # Shuffles the presentation order for the students
        random.shuffle(lst)

        #for (final, value) in get_type(qt.t_grading, keytype='final'):
        #    lst.append(template % (q_type, name, value, final))

        # NOTE: Do not use <div> tags: content inside it is ignored by Markdown
        #       Causes math not to be rendered.
        lst.insert(0, '<span class="quest-question-mcq">')
        lst.append('</span>')
        return lst
    #---------
    def render_short_question(qt):
        """Renders short-answer questions. More than one short answer box may
        be present.
        """
        ans_str = '<input type="text" name="%s"></input>'
        out = ''
        token_dict = {}
        token = re.compile(r'\{\[(.*?)\]\}')
        if token.findall(qt.t_question):

            start = 0
            for item in token.finditer(qt.t_question):
                out += qt.t_question[start:item.start()]
                key = item.groups()[0]
                val = generate_random_token(8)
                try:
                    token_dict[val] = qt.t_grading.pop(key)  # transfer it over
                except KeyError:
                    if not(key):
                        logger.error(('You forget to specify the variable '
                                    'in the question [%s]') % qt.name)
                    else:
                        logger.error(('Error when rendering template %s:  '
                              'could not find key [%s] in the grading dict') %
                                     (qt.name, key))
                    raise

                out += ans_str % val
                start = item.end()

            if out:
                out += qt.t_question[start:]

        return out, token_dict
    #---------
    def render_peer_evaluation(qt):
        """ Render the qt.t_question field into the Markdown necessary for
        a peer evaluation.

        The question can have

        lines before
        lines before
        -*-
        repeated parts for each user
        repeated parts for each user
        -*-
        lines after
        lines after
        """
        token_dict = {}
        if not options:
            return (('This question does not apply; you were not working in a '
                                 'group.'), token_dict)
        peers = options['peers']
        if not(peers):
            return (('This question does not apply; you were not working in a '
                     'group.'), token_dict)
        out = []
        question = qt.t_question.split('\n')
        repeated = ''
        before = ''
        after = ''
        mode = 'before'
        for line in question:
            if line.startswith('-*-'):
                if mode == 'before':
                    mode = 'repeat'
                else:
                    mode = 'after'
            else:
                if mode == 'before':
                    before += line + '\n'
                elif mode == 'repeat':
                    repeated += line + '\n'
                elif mode == 'after':
                    after += line + '\n'

        repeated += "<hr>\n"  # The "\n" helps with the markdown creation

        ranking = """<table border="0" cellpadding="5" cellspacing="0"><tbody>
        <tr>
        <td class="quest-sn"></td>
        <td class="quest-sn"><label for="{{person_slug}}_0">0</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_1">1</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_2">2</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_3">3</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_4">4</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_5">5</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_6">6</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_7">7</label></td>
        <td class="quest-sn"><label for="{{person_slug}}_8">8</label></td>
        <td class="quest-sn"></td>
        </tr><tr>
        <td class="quest-sr ss-leftlabel">No show</td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="0" class="quest-qr" id="{{person_slug}}_0"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="1" class="quest-qr" id="{{person_slug}}_1"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="2" class="quest-qr" id="{{person_slug}}_2"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="3" class="quest-qr" id="{{person_slug}}_3"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="4" class="quest-qr" id="{{person_slug}}_4"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="5" class="quest-qr" id="{{person_slug}}_5"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="6" class="quest-qr" id="{{person_slug}}_6"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="7" class="quest-qr" id="{{person_slug}}_7"></input></td>
        <td class="quest-sr"><input type="radio" name="pf__{{person_slug}}" value="8" class="quest-qr" id="{{person_slug}}_8"></input></td>
        <td class="quest-sr ss-rightlabel">Excellent [note: 6 is very satisfactory]</td>
        </tr></tbody></table>
        """
        out.append(before)
        out.append("<hr>\n",)
        for peer, person_slug in peers:
            slug = person_slug.replace('-', '_')
            out.append(repeated.replace('--ranking--', ranking)\
                                        .replace('{{person}}', '**'+peer+'**')\
                                        .replace('{{person_slug}}', slug)\
                                        .replace('person_slug', slug))

        out.append(after)
        out = '\n'.join(out)

        # Add the textarea where required
        tarea = re.compile(r'\{\[\[(.*?)\]\]\}')
        textarea = '<textarea name="%s" cols="100" rows="3"></textarea>'
        fout = ''
        start = 0
        for segment in tarea.finditer(out):
            key = segment.groups()[0]
            val = generate_random_token(8)
            token_dict[val] = key
            fout += out[start:segment.start()] + textarea % (val)
            start = segment.end()
        fout += out[start:]
        return fout, token_dict
    #---------
    def call_markdown(text, filenames):
        """
        Calls the Markdown library http://daringfireball.net/projects/markdown

        The ``filenames`` dict contains a mapping from any found filenames to
        their rendered location (relative to the server's MEDIA location).

        The keys of this dict are the original filename and the value is the
        new, correct location. However it is up to another function to move
        the files into the correct place.
        """
        # Special filter: to ensure "\\" in the input string actually comes
        # out as intended, as "\\"
        text = text.replace('\\', r'\\\\')

        # Call Markdown to do the HTML formatting for us
        out = markdown.markdown(text)

        # Post processing of ALL image fields (multiple might exist)
        # <img alt="Image alt text" src="image_file_name.jpg" />
        img = re.compile(r'<img(.*?)src="(.*?)"')
        mod_out = ''
        start = 0
        for image in img.finditer(out):
            mod_out += out[start:image.start()] + r'<img' + image.group(1)
            hashm = hashlib.md5()
            hashm.update(image.group(2))
            root = settings.QUEST['MEDIA_LOCATION'] % hashm.hexdigest()[0]
            filenames[image.group(2)] = root + image.group(2)
            mod_out += 'style="width: 100%" src="{0}"'.format(settings.MEDIA_URL + \
                                hashm.hexdigest()[0] + '/' + image.group(2))
            start = image.end()

        if mod_out:
            out = mod_out + out[start:]

        # Undo the filtering in the HTML
        return out.replace('\\\\', '\\'), filenames
    #---------
    def clean_diplayed_answer(item, sig_figs=None):
        """
        Cleans any type of input data to ensure a string output is sent back.
        """
        from decimal import Decimal, Context
        from math import log10, floor
        if not(sig_figs):
            step =4
            sig_figs = int(abs(floor(log10(step/1000.0))))


        if isinstance(item, (float, int)):
            out = [[],str(item)]

        if isinstance(item, basestring):
            out = [[], item]

        if isinstance(item, list) or isinstance(item, np.ndarray):
            # TODO(KGD): ndarrays of 2 or more dimensions should be formatted
            #            is a 2D array
            out = []
            for entry in item:
                temp = Context(prec=sig_figs, Emax=999,).\
                                    create_decimal(str(entry))
                out.append(float(temp))

            out = [[],str(out)]  # so that it can correctly work with the
                                  # subsequent ``insert_evaluate_variables()``

        return out
    #---------

    # 1. Convert to strings
    if isinstance(qt.t_grading, basestring) and qt.t_grading :
        qt.t_grading = json.loads(qt.t_grading)
    if isinstance(qt.t_variables, basestring) and qt.t_variables:
        qt.t_variables = json.loads(qt.t_variables)

    # 2. Random variables, if required.
    var_dict = {}
    if qt.t_variables:
        var_dict = create_random_variables(qt.t_variables)

    # 3. Evaluate source code
    # The source code will expand the random variables in the dictionary that
    # are particular to this user. It will also potentially create
    # grading solutions.
    new_variables, grading_variables = evaluate_template_code(qt.t_code,
                                                              var_dict)
    for key, value in new_variables.iteritems():
        var_dict[key] = clean_diplayed_answer(value)
    for key, value in grading_variables.iteritems():
        qt.t_grading[key] = value


    # 4. Render the HTML
    rndr_question = []
    grading_answer = {}
    if qt.q_type in ('mcq', 'tf', 'multi'):
        rndr_question.append(qt.t_question)
        rndr_question.append('\n')
        rndr_question.extend(render_mcq_question(qt))
    elif qt.q_type == 'long':
        rndr_question.append(qt.t_question)
        rndr_question.append('\n')
        ans_str = ('<textarea name="%s" cols="100" rows="10" '
                   'autofocus="true", placeholder="%s">'
                   '</textarea>') % (generate_random_token(8),
                                     'Enter your answer here ...')
        rndr_question.append(ans_str)
    elif qt.q_type == 'short':
        out, grading_answer = render_short_question(qt)
        rndr_question.append(out)
    elif qt.q_type == 'peer-eval':
        out, var_dict = render_peer_evaluation(qt)
        rndr_question.append(out)
        rndr_question.append('\n')


    # 5. Evalute the solution string
    rndr_solution = qt.t_solution

    # 5. Now call Django's template engine to render any templates, only if
    #    there are variables to be rendered
    if var_dict:
        try:
            rndr_question = insert_evaluate_variables(rndr_question, var_dict)
            rndr_solution = insert_evaluate_variables(rndr_solution, var_dict)
        except Exception, e:
            raise(e)

    else:
        rndr_question = '\n'.join(rndr_question)


    # 6. Then call Markdown
    filenames = {}
    html_q, filenames = call_markdown(rndr_question, filenames)
    html_a, filenames = call_markdown(rndr_solution, filenames)

    # 7. Dump the dictionary to a string for storage
    var_dict_str = json.dumps(var_dict, separators=(',', ':'), sort_keys=True)
    grading_answer = json.dumps(grading_answer, separators=(',', ':'),
                                sort_keys=True)

    # TODO(KGD): move the images in ``filenames``

    return html_q, html_a, var_dict, grading_answer


def create_random_variables(var_dict):
    """
    The ``var_dict`` is augmented with the randomly selected value.

    Before:
    {'a': [[ -5,   3,   2, int,   uniform], None],
     'b': [[2.4, 2.7, 0.1, float, normal], None],
     'c': [[  1,   2, 0.5], None],                   <--- minimal specifcation
     'd': [[-Inf, Inf, 1E10], None],    <--- valid specification, depends on
                                             whether it's a float or int type
    }
    indicates we have a variable ``a`` to select that must be taken from the
    uniform distribution, and must come from the set: [-5, -3, -1, +1, 3],
    where the value to select must be from a uniform distribution. The
    variable ``b`` must be from [2.4, 2.5, 2.6, 2.7] and values should be
    normally distributed (i.e. 2.5 and 2.6 are going to appear more frequently
    than 2.4 and 2.7.

    The minimal specification will assume floating point and use random
    numbers from the uniform distribution.

    The values selected will take the place of ``None`` in the above list, so
    that if a non-None already exists there it will be simply overwritten.
    """
    for key, val in var_dict.iteritems():
        if isinstance(val[0], list):
            spec = val[0]
        elif isinstance(val[0], dict):
            spec = val[0]
            var_dict[key] = [spec, None]
        else:
            spec = val
            var_dict[key] = [spec, None]

        if len(spec) == 3:
            lo, hi, step = spec
            v_type = 'float'
            dist = 'uniform'
        elif len(spec) == 4:
            lo, hi, step, v_type = spec
            dist = 'uniform'
        elif len(spec) == 5:
            lo, hi, step, v_type, dist = spec
        elif len(spec) == 1:
            # It's a "choices" dict. Randomly choose one of the entries in it
            var_dict[key][1] = random.choice(spec['choices'])
            continue
        else:
            raise BadVariableSpecification(('Specification list should be 3 '
                                            'or more entries'))

        dist = dist.strip().lower()
        v_type = v_type.strip().lower()

        # If the user is trying to specify a constant variable as
        # [2.39, 2.39, 0.0], i.e. lo=2.39, hi=2.39, step=0.0
        # this it will (rightly) fail. The user should just hard-code the
        # value, since it isn't a variable anymore; it's a constant.
        if lo > hi:
            raise BadVariableSpecification(('[low, high, step]: low < high'))
        if step > (hi-lo):
            raise BadVariableSpecification(('[low, high, step]: step < '
                                            '(low - high'))

        if np.isinf(lo):
            if v_type == 'int':
                lo = np.iinfo(v_type).min
            elif v_type == 'float':
                lo = np.finfo(v_type).min

        if np.isinf(hi):
            if v_type == 'int':
                hi = np.iinfo(v_type).max
            elif v_type == 'float':
                hi = np.finfo(v_type).max

        if dist in ('uniform', 'unif'):
            rnd_val = np.random.uniform()
        elif dist in ('normal', 'norm'):
            # Map the range from 0 to 1.0 into the normal distribution centered
            # at 0.5 and sd=1/6*(1.0 - 0)
            rnd_val = np.random.normal(loc=0.5, scale=1.0/6.0)
        else:
            rnd_val = ('Please specify either "uniform" or "normal" as the '
                       'random variable type.')


        temp = rnd_val * (hi - lo)
        # Randomly round ``temp`` down or round up:
        # e.g. [60, 100, 8] and if rnd_val = 0.25, then temp = 0.25*40 = 10
        #      we can legimately choose 68 or 76 to round towards. Make this
        #      a random decision, so we are not biased
        if np.random.rand() < 0.5:
            temp = np.floor(temp/(step+0.)) * step + lo
        else:
            temp = np.ceil(temp/(step+0.)) * step + lo

        # Final check on the bounds. This code shouldn't really ever be run
        if temp > hi:
            temp = hi
        if temp < lo:
            temp = lo

        #from decimal import Decimal, Context
        #from math import log10, floor
        #step =4
        #sig_figs = int(abs(floor(log10(step/1000.0))))
        #out = Context(prec=sig_figs, Emax=999,).create_decimal(str(temp))
        #out = out.to_eng_string()
        #if v_type == 'int':
        #    var_dict[key][1] = np.int(np.float(out))

        if v_type == 'int':
            var_dict[key][1] = np.int(temp)
        else:
            var_dict[key][1] = float(temp)

    return var_dict


def clean_db(request):
    """
    During week-2 the database got corrupted; this is an attempt to clean it.
    """
    from django.core import serializers
    from question import models
    #from person.models import User
    #import sys
    #qset = models.QSet.objects.all()
    import gc

    for idn in range(1479, 1489):
        quests = models.QActual.objects.filter(id=idn)
        data = serializers.serialize("json", quests, indent=2)
        out = open("/home/kevindunn/quest/jsons/quests-week-2-400-temp.json", "w")
        out.write(data)
        out.close()



    ##users =
    #for idx, user in enumerate(User.objects.all()):
        #gc.collect()
        #print(idx, user)
        #sys.stdout.flush()
        #if user.id !=37:
            #continue

        ##quests = models.QActual.objects.filter(qset=qset[1], user=user)
        #quests = models.QActual.objects.filter(id=892)


        #data = serializers.serialize("json", quests, indent=2)
        #out = open("/home/kevindunn/quest/jsons/quests-week-2-400-temp.json", "w")
        #out.write(data)
        #out.close()

        infile = open("/home/kevindunn/quest/jsons/quests-week-2-400-temp.json", "r")
        outfile = open("/home/kevindunn/quest/jsons/quests-week-2-600-cleaned.json", "a")
        for line in infile.xreadlines():
            print(line[0:min(50, len(line))])

            if len(line) > 335544412//3:
                a = len(line)//3
                test1 = line[0:a].strip().replace('"var_dict": ', '').strip(',')
                out = ''
                for item in test1:
                    if item not in ('\\', r'"'):
                        out += item
                del test1
                gc.collect()
                print out

                test2 = line[a:2*a].strip().replace('"var_dict": ', '').strip(',')
                for item in test2:
                    if item not in ('\\', r'"'):
                        out += item
                del test2
                gc.collect()
                print out

                test3 = line[2*a:].strip().replace('"var_dict": ', '').strip(',')
                for item in test3:
                    if item not in ('\\', r'"'):
                        out += item
                del test3
                gc.collect()
                print out

                line = '      "var_dict": ' + '{"n_sample": [[4.0, 6.0, 1.0, "int"], 6], "n_total": [[6.0, 10.0, 1.0, "int"], 7]}'


            if line.strip().startswith('"var_dict"'):
                test = line.strip().replace('"var_dict": ', '').strip(',')
                k = 0
                while isinstance(test, basestring):
                    test = json.loads(test)
                    k+=1
                print(k)

                output = json.dumps(test)
                outfile.write('      "var_dict": ' + output + ',\n')
            else:
                if line in ('[]', '[\n'):
                    pass
                elif line in (']\n'):
                    outfile.write(',')
                else:
                    outfile.write(line)


        outfile.close()
        infile.close()

        #for idx in range(len(line)//1000000):
            #print(line[idx*1000:(idx+1)*1000])
            #print(idx)
            #sys.stdout.flush()

            #{n_sample: [[4.0, 6.0, 1.0, '

def fix_questions(request):
    """
    Fix an error in a question.
    """
    #for qa in QActual.objects.filter(qtemplate__id=21):
        #qa.html_solution = u'<p>The average is \\(\\bar{x} = 49.6\\) and the standard deviation is \\(s=18.18\\). Use the \\(t\\)-distribution with 9 degrees of freedom to find the critical value, \\(c_t = 2.262\\) [found with R using <code>qt(0.975, 9)</code>]. </p>\n<p>Then the lower bound is \\(\\bar{x} - c_t \\dfrac{s}{\\sqrt{n}} = 49.6 - 2.262 \\dfrac{18.18}{\\sqrt{10}} = 36.6\\) and the upper bound is \\(49.6 + 2.262 \\dfrac{18.18}{\\sqrt{10}} = 62.6\\).</p>'
        #qa.save()
        #logger.debug('Fixed question %d' % qa.id)

    #for qa in QActual.objects.filter(qtemplate__id=42):
        #ga = json.loads(qa.grading_answer)
        #for key, value in ga.iteritems():
            #value = eval(value[0])
            #value[1] = 0.1
            #ga[key] = [json.dumps(value), ]
        #qa.grading_answer = json.dumps(ga)
        #qa.save()

    #for qa in QActual.objects.filter(qtemplate__id=43):
        #ga = json.loads(qa.grading_answer)
        #for key, value in ga.iteritems():
            #value = eval(value[0])
            #if value[1] > 0:
                #value[1] = 0.1
            #ga[key] = [json.dumps(value), ]
        #qa.grading_answer = json.dumps(ga)
        #qa.save()

    for qa in QActual.objects.filter(qtemplate__id=58):
        price = int(qa.as_displayed[88:qa.as_displayed.find('.')])
        book_value = price - price * 0.2 / 2.0
        ga = json.loads(qa.grading_answer)
        for key, value in ga.iteritems():
            ga[key][0] = book_value
        qa.grading_answer = json.dumps(ga)

        qa.html_solution = '<p>The book value is $%d.</p>' % book_value
        qa.save()


def preview_question(request):    # URL: ``admin-preview-question``
    """
    Allows an admin user to repeatedly preview a question
    """
    if request.method == 'GET' and not(request.GET):
        ctxdict = {}
        ctxdict.update(csrf(request))
        return render_to_response('instructor/preview-question.html', ctxdict,
                                  context_instance=RequestContext(request))
    elif request.method == 'GET' and request.GET.has_key('qtemplate'):
        qtemplate = request.GET['qtemplate']
        question = qtemplate.split('#----')
        if len(question) > 1 and question[0].strip() == '':
            question = question[1]
        elif len(question) == 1:
            question = question[0]

        preview_user = UserProfile.objects.filter(slug='quest-grader-previewer')[0]
        # Clear out database from previews more than a day old
        for item in QActual.objects.filter(user=preview_user):
            if item.last_edit + datetime.timedelta(seconds=60*60*24) < \
                                                    datetime.datetime.now():
                item.delete()

        for item in QTemplate.objects.filter(contributor=preview_user):
            if item.when_uploaded + datetime.timedelta(seconds=60*60*24) < \
                                                    datetime.datetime.now():
                item.delete()


        for item in QActual.objects.filter(qtemplate__name=\
                                                request.COOKIES['sessionid']):
            item.delete()

        for item in QTemplate.objects.filter(name=\
                                               request.COOKIES['sessionid']):
            item.delete()


        template = create_question_template(question, user=preview_user)

        # Abuse the template's name to contain the user's token.
        # We will use this to validate the question for preview grading
        template.name = request.COOKIES['sessionid']
        template.save()


        # Now render the template, again, without hitting the database
        html_q, html_a, var_dict, grading_answer = render(template)

        qa = QActual.objects.create(qtemplate=template,
                                    qset=None,
                                    user=preview_user,
                                    as_displayed=html_q,
                                    html_solution=html_a,
                                    var_dict=var_dict,
                                    grading_answer=grading_answer)

        ctxdict = {'quest_list': [],
                   'item_id': 'Preview',
                   'course': None,
                   'qset': None,
                   'item': qa,
                   'timeout_time': 500,       # in the HTML template, XHR timeout
                   'minutes_left': 0,
                   'seconds_left': 0,
                   'html_question': html_q,
                   'html_solution': html_a,
                   'last_question': True}
        ctxdict.update(csrf(request))
        return render_to_response('question/single-question.html', ctxdict,
                                  context_instance=RequestContext(request))
    elif request.method == 'GET' and request.GET.get('preview', '') == 'True':
        # Preview user is wanting to check grading
        preview_user = UserProfile.objects.filter(\
                                            slug='quest-grader-previewer')[0]
        for idx, item in enumerate(QActual.objects.filter(user=preview_user)):
            if item.qtemplate.name == request.COOKIES['sessionid']:
                # We've found the QActual corresponding to the QActual being
                # viewed
                do_grading(item)
                return HttpResponse(str(item.grade))




