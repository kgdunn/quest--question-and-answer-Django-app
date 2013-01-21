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
from collections import defaultdict

from django.conf import settings
from django.shortcuts import HttpResponse
from django.core.exceptions import ValidationError
from django.template import Context, Template, Library
from django.contrib.auth.decorators import login_required
register = Library()

# 3rd party imports
import markdown
import numpy as np

# Our imports
from question.models import (QTemplate, QActual, Inclusion)
from question.views import validate_user
from person.models import (UserProfile, User)
from person.views import create_sign_in_email
from tagging.views import get_and_create_tags
from utils import generate_random_token, send_email
from course.models import Course

logger = logging.getLogger('quest')
logger.debug('Initializing quest::question::views.py')


class BadVariableSpecification(Exception): pass

# TODO(KGD): allow these to be case-insenstive later on
CONTRIB_RE = re.compile(r'^Contributor:(\s*)(.*)$')
TAGS_RE = re.compile(r'^Tags:(\s*)(.*)$')
DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(.*)$')
GRADES_RE = re.compile(r'^Grade:(\s*)(.*)$')
FEEDBACK_RE = re.compile(r'^Feedback:(\s*)(.*)$')

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

        for line in text:

            # This check must be before the next one
            if line.startswith('%^'):
                section_name = generate_random_token(4)
                t_grading[section_name] = ['final-key', ]
                final = FINALKEY_RE.match(line).group(2)
                t_grading[section_name].append(final)
                continue

            elif line.startswith('%'):
                section_name = generate_random_token(4)
                t_grading[section_name] = ['final-lure', ]
                final = FINALLURE_RE.match(line).group(2)
                t_grading[section_name].append(final)
                continue

            elif line.startswith('^'):
                section_name = generate_random_token(4)
                t_grading[section_name] = ['key', ]
                key = KEY_RE.match(line).group(2)
                t_grading[section_name].append(key)
                continue

            elif line.startswith('&'):
                section_name = generate_random_token(4)
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


def parse_OTHER(text, solution, grading, q_type):             # helper
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
    if q_type in ('short', 'long', 'multipart'):
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
    t_question = t_solution = t_grading = var_dict = ''
    # Force it into a list of strings.
    if isinstance(text, basestring):
        text = text.split('\n')

    # ``sd`` = section dictionary; see comments for function below.
    sd = split_sections(text)

    # These items are mandatory
    if not sd.has_key('type'):
        raise ParseError('[[type]] section not given')
    if not sd.has_key('question'):
        raise ParseError('[[question]] section not given')

    if isinstance(sd['type'], list):
        sd['type'] = ''.join(sd['type']).strip().lower()
    elif isinstance(sd['type'], basestring):
        sd['type'] = sd['type'].strip().lower()

    if sd['type'] in ('tf', 'mcq', 'multi'):
        t_question, t_solution, t_grading = parse_MCQ_TF_Multi(sd['question'],
                                                               sd['type'])
        if sd.has_key('solution'):
            t_solution += '\n\n' + '\n'.join(sd['solution'])

        sd.pop('question')

    if sd['type'] in ('short', 'long', 'multipart'):
        if not sd.has_key('solution'):
            raise ParseError(('[[solution]] section not given for %s question'
                              ' [%s...]') % (sd['type'],
                                            str(sd['question'])[0:30]))
        if not sd.has_key('grading'):
            raise ParseError(('[[grading]] section not given for %s question'
                              ' [%s...]. Required to assist person grading') %\
                            (sd['type'], str(sd['question'])[0:30]))

        # This function really doesn't do anything. Placeholder for now
        # Remmber that ``parse_question_text()`` is intended only to load
        # text templates into our internal representation. Text templates
        # match our internal representation closely anyway.
        # We render the question and solution later.
        t_question, t_solution, t_grading = parse_OTHER(sd['question'],
                                                        sd['solution'],
                                                        sd['grading'],
                                                        sd['type'])

    sd['contributor'] = 1
    sd['tags'] = ''
    sd['difficulty'] = 1
    sd['max_grade'] = 1
    sd['feedback'] = True
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

            if FEEDBACK_RE.match(line):
                sd['feedback'] = FEEDBACK_RE.match(line).group(2).lower() \
                                                                     == 'true'

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
        sd['name'] = t_question.replace('\n','').strip()

    sd['t_question'] = t_question
    sd['t_solution'] = t_solution
    sd['t_grading'] = t_grading
    sd['t_variables'] = var_dict

    return sd


def create_question_template(text, user=None):
    """
    Creates the QTemplate (question template) and adds it to the database.
    """
    sd = parse_question_text(text)
    contributor = user or UserProfile.objects.filter(role='Grader')[0]

    # Maybe we've imported this template before. Update the previous ones.
    exist = QTemplate.objects.filter(name=sd['name'], contributor=contributor,
                                     q_type=sd['type'])
    if exist:

        # DO NOT EVER OVERWRITE AN EXISTING QTEMPLATE.
        # It will break the grading for questions that are in progress, but
        # not graded yet.

        logger.warn(('Found an existing question with the same/similar '
                     'template. Skipping it: [%s]') % sd['name'])

        # Return only the first instance of the template (there should only
        # be one anyway)
        qtemplate = exist[0]

    else:
        qtemplate = QTemplate.objects.create(name=sd['name'],
                            q_type=sd['type'],
                            contributor=contributor,
                            difficulty=sd['difficulty'],
                            max_grade = sd['max_grade'],
                            enable_feedback = sd['feedback'],
                            t_question = sd['t_question'],
                            t_solution = sd['t_solution'],
                            t_grading = sd['t_grading'],
                            t_variables = sd['t_variables'] )

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


@login_required                       # URL: ``admin-load-question-templates``
def load_question_templates(request, course_code_slug, question_set_slug):
    """
    Given a text file, loads various question templates for a course.

    Each question is split by "#----" in the text file
    """
    # http://localhost/_admin/load-from-template/4C3-6C3/week-1/

    f_name = '/home/kevindunn/quest/week-2.qset'
    f_name = ''
    course = validate_user(request, course_code_slug, question_set_slug,
                           admin=True)
    if isinstance(course, HttpResponse):
        return course
    if isinstance(course, tuple):
        course, qset = course

    if not f_name:
        return HttpResponse('No templates loaded')

    f_handle = open(f_name, 'r')
    questions = f_handle.read().split('#----')
    f_handle.close()

    for question in questions:
        template = create_question_template(question,
                                            user=request.user.get_profile())
        included_item = Inclusion(qset=qset, qtemplate=template)
        try:
            included_item.save()
        except ValidationError, e:
            logger.warn(('This template [%d] has already been included in '
                         'this question set [%s]') % (template.id, qset.name))

    return HttpResponse('All questions loaded')

@login_required                             # URL: ``admin-generate-questions``
def generate_questions(request, course_code_slug, question_set_slug):
    """
    1. Generates the questions from the question sets, rendering templates
    2. Emails users in the class the link to sign in and start answering
    """
    #fname = '/home/kevindunn/quest/class-list.csv'
    #fname = ''
    #if fname:
    #    users_added = load_class_list(fname, course_code_slug)

    load_question_templates(request, course_code_slug, question_set_slug)

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
            qts = qset.include.all()

        question_list = []
        for idx, qt in enumerate(qts):
            qa = QActual.objects.filter(qtemplate=qt.qtemplate,
                                        qset=qset,
                                        user=user.get_profile(),
                                        is_submitted=False)
            question_list.extend(qa)
            if len(qa) == 0:
                qa = render(qt.qtemplate, qset, user)
                question_list.append(qa)

        n_questions = len(qts)

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

    if True:
        to_list = []
        message_list = []
        out = subject = ''
        for user in user_objs:
            subject, message, to_address = create_sign_in_email(user, qset)
            message_list.append(message)
            to_list.append(to_address)

        if to_list:
            out = send_email(to_list, subject, message_list)
        if out:
            logger.debug('Successfully sent multiple emails for sign in to %s'
                         % str(to_list))
        else:
            logger.error('Unable to send multiple sign-in emails to: %s' %
                        str(to_list))

    return HttpResponse('All questions generated for all users for %s' % qset.slug)


def render(qt, qset, user):
    """
    Renders templates to HTML.
    * Handles text
    * MathJax math
    * Pictures/images
    * Calls external code before rendering
    * Create a QActual object, which is returned

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
        for (key, value) in get_type(qt.t_grading, keytype='key'):
            lst.append(template % (q_type, name, value, key))

        for (lure, value) in get_type(qt.t_grading, keytype='lure'):
            lst.append(template % (q_type, name, value, lure))

        random.shuffle(lst)
        for (final, value) in get_type(qt.t_grading, keytype='final'):
            lst.append(template % (q_type, name, value, final))

        # Do not use <div> tags: content inside it is ignore by Markdown
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
                token_dict[val] = qt.t_grading.pop(key)  # transfer it over
                out += ans_str % val
                start = item.end()

            if out:
                out += qt.t_question[start:]

        return out, token_dict
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
            mod_out += 'src="%s"' % (settings.MEDIA_URL + \
                                hashm.hexdigest()[0] + '/' + image.group(2))
            start = image.end()

        if mod_out:
            out = mod_out + out[start:]

        # Undo the filtering in the HTML
        return out.replace('\\\\', '\\'), filenames
    #---------
    def insert_evaluate_variables(text, var_dict):
        """
        Uses the Django template library to insert and evaluate expressions.
        A list of strings and the variable dictionary of key-value pairs to
        insert must be provided.
        """
        if isinstance(text, list):
            text.insert(0, '{% load quest_render_tags %}')
            rndr_string = '\n'.join(text)
        else:
            rndr_string = r'{% load quest_render_tags %}' + text

        var_dict_rendered = {}
        for key, values in var_dict.iteritems():
            var_dict_rendered[key] = values[1]

        tmplte = Template(rndr_string)
        cntxt = Context(var_dict_rendered)
        return tmplte.render(cntxt)

    # 1. First convert strings to dictionaries:
    if isinstance(qt.t_grading, basestring):
        qt.t_grading = json.loads(qt.t_grading)
        qt.t_variables = json.loads(qt.t_variables)

    rndr_question = []
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
        out, token_dict = render_short_question(qt)
        rndr_question.append(out)
    elif qt.q_type == 'multipart':
        rndr_question.append(qt.t_question)
        rndr_question.append('\n')


    # 2. Random variables, if required.
    var_dict = {}
    if qt.t_variables:
        var_dict = create_random_variables(qt.t_variables)

    # 3. Evaluate source code
    # TODO(KGD)
    pass

    # 4. Evalute the solution string
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


    # TODO(KGD): move the images in ``filenames``

    qa = QActual.objects.create(qtemplate=qt,
                                qset=qset,
                                user=user.get_profile(),
                                as_displayed=html_q,
                                html_solution=html_a,
                                var_dict=var_dict)

    return qa


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

        if dist == 'uniform':
            rnd_val = np.random.uniform()
        elif dist == 'normal':
            # Map the range from 0 to 1.0 into the normal distribution centered
            # at 0.5 and sd=1/6*(1.0 - 0)
            rnd_val = np.random.normal(loc=0.5, scale=1.0/6.0)

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
        #sig_figs = abs(floor(log10(step/1000.0)))
        #out = Context(prec=sig_figs, Emax=999,).create_decimal(str(temp))
        #out = out.to_eng_string()
        #if v_type == 'int':
        #    var_dict[key][1] = np.int(np.float(out))

        if v_type == 'int':
            var_dict[key][1] = np.int(temp)
        else:
            var_dict[key][1] = float(temp)

    return var_dict


def auto_grade():
    """
    Auto-grades a question set.
    * Questions that cannot be auto-graded are distinctly shown as not
      graded yet
    """
    pass


def load_class_list(f_name, course_slug):
    """
    Load a CSV file class list (exported from Avenue via copy/paste to textfile)
    LASTNAME, FIRSTNAME,email.prefix,0001231  <-- student number
    """
    # These fields require list drop-downs and validation. They are hard coded
    # for now
    course = Course.objects.filter(slug=course_slug)[0]
    email_suffix = '@mcmaster.ca'

    f_handle = open(f_name, 'rb')
    #with open(f_name, 'rb') as csvfile:
    users_added = []
    rdr = csv.reader(f_handle, delimiter=',')
    for row in rdr:
        last, first, email_id, student_id = row
        username = '%s-%s' % (first.strip().lower(),
                              last.strip().lower())

        if '@' not in email_id:
            email = email_id+email_suffix
        else:
            email = email_id
        try:
            obj = User.objects.get(email=email)
        except User.DoesNotExist:
            obj = User(username=username,
                       first_name=first.strip(),
                       last_name=last.strip(),
                       email=email_id+email_suffix)
            obj.save()
            logger.info('Created user for %s with name: %s' % (course_slug,
                                                               username))
            users_added.append(obj)

        profile = obj.get_profile()
        profile.role = 'Student'
        profile.student_number = student_id.strip()
        profile.courses.add(course)
        profile.save()

    return users_added


