# -*- coding: utf-8 -*-

# Python and Django imports
import re
import json
import random
from lxml import etree
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response, redirect

# 3rd party imports
import markdown


# Our imports
from models import (QTemplate, QSet, QActual)
from person.models import UserProfile
from tagging.views import get_and_create_tags
from utils import generate_random_token
from course.models import Course

# TODO(KGD): allow these to be case-insenstive later on
CONTRIB_RE = re.compile(r'^Contributor:(\s*)(.*)$')
TAGS_RE = re.compile(r'^Tags:(\s*)(.*)$')
DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(.*)$')
GRADES_RE = re.compile(r'^Grade:(\s*)(.*)$')
FEEDBACK_RE = re.compile(r'^Feedback:(\s*)(.*)$')

LURE_RE = re.compile(r'^\&(\s*)(.*)$')
KEY_RE = re.compile(r'^\^(\s*)(.*)$')
FINAL_RE = re.compile(r'^\&(\s*)(.*)$')

class ParseError(Exception):
    pass


def split_sections(text):
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


def parse_MCQ_TF_Multi(text):
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
    t_question = ''.join(instructions)

    # Handles the case of the """--\n--\n""" where we specify the solution in
    # terms of a function.
    if text[0].strip() == '--':
        t_solution = ''
        t_grading = '<function>'
    else:
        t_solution = ''
        t_grading = dict()

        for line in text:
            if line.startswith('%'):
                section_name = generate_random_token(4)
                t_grading[section_name] = ['final', ]
                final = FINAL_RE.match(line).group(2)
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

    return t_question, t_solution, t_grading


def parse_question_text(text):
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
    & 12    <-- distractors (lures) begin with "&"
    & 1     <-- distractor
    ^2      <-- correct answer(s) begin with "^"
    & 4     <-- distractor
    % None  <-- an option that must be presented last begins with "%"

    [[variables]]

    """
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
        t_question, t_solution, t_grading = parse_MCQ_TF_Multi(sd['question'])
        sd.pop('question')

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

    # Final checks before returning
    if not sd.has_key('name'):
        sd['name'] = t_question

    sd['t_question'] = t_question
    sd['t_solution'] = t_solution
    sd['t_grading'] = t_grading
    sd['t_variables'] = {}

    return sd


def create_question_template(text):
    """
    Creates the QTemplate (question template) and adds it to the database.
    """
    sd = parse_question_text(text)
    contributor = UserProfile.objects.filter(role='Grader')[0] or None

    qtemplate = QTemplate.objects.create(name=sd['name'], q_type=sd['type'],
                             contributor=contributor,
                             difficulty=sd['difficulty'],
                             max_grade = sd['max_grade'],
                             enable_feedback = sd['feedback'],
                             t_question = sd['t_question'],
                             t_solution = sd['t_solution'],
                             t_grading = sd['t_grading'],
                             t_variables = sd['t_variables']
                            )

    for tag in get_and_create_tags(sd['tags']):
        qtemplate.tags.add(tag)

    return qtemplate


def generate_questions(course_code, qset_name):
    """
    1. Generates the questions from the question sets, rendering templates
    2. Emails students in the class the link to sign in and start answering
    """

    # Remember to copy over the rendered HTML to the question and the q_variables
    # dict used in the template
    course = Course.objects.filter(code=course_code)
    qset = []
    if course:
        qset = QSet.objects.filter(name=qset_name).filter(course=course[0])

    if not qset:
    # TODO(KGD): raise error: course and qset not found
        return

    # Now render, for every student, their questions from the question set
    for user in UserProfile.objects.filter(courses=course):

        # TODO(KGD): handle the randomization of questions here
        # ``qts`` = question templates
        qts = qset[0].qtemplates.all()

        for qt in qts:
            html, vardict = render(qt)
            qa = QActual.objects.create(qtemplate=qt, qset=qset[0],
                                        user=user, as_displayed=html,
                                        var_dict = vardict)
            print(qa)

@login_required
def ask_question_set(request):
    """
    Ask which question set to display
    """
    user = request.user.profile
    qsets = []
    for course in user.courses.all():
        # Which course(s) is the user registered for? Get all the QSet's for them
        qsets.extend(course.qset_set.all())

    # Sort them from most current to earliest (reverse time order)
    qset_order = [q.ans_time_start for q in qsets]
    qset_order.sort()

    # Show question sets

    # Assume user has clicked on the question set
    # Show all the questions


    from django import template
    from django.template.defaultfilters import stringfilter
    register = template.Library()
    #@register.filter
    #@stringfilter
    #def lower(value):
        #return value.lower()

    #g = """{% load core_tags %} x + y = {% eval %} {{x}} + {{y}} {% endeval %}"""
    g = """{% load core_tags %} x + y = {% evaluate %}\n a=x+y\n b=a+4\n return b {% endeval %}"""
    g = """{% load core_tags %} x + y = {% quick_eval "x/y" 5 %}"""
    from django.template import Context, Template
    t = Template(g)
    c = Context({'x':4, 'y':20})
    r = t.render(c)
    print(r)









    return redirect('quest-ask-questions', '4C3-6C3', 'week-1')

@login_required
def ask_show_questions(request, course_code_slug, question_set_slug):
    """
    Display questions (and perhaps answers) to questions from a question set
    for a specific student
    """
    user = request.user.profile
    courses = Course.objects.filter(slug=course_code_slug)
    if not courses:
        # TODO(KGD): redirect to login page
        return

    qset=QSet.objects.filter(slug=question_set_slug).filter(course=courses[0])
    if not qset:
        # TODO(KGD): redirect to login page
        return

    # Show all the questions for this student
    quests = QActual.objects.filter(qset=qset[0]).filter(user=user)

    # Now display the questions



def render(qt):
    """
    Renders templates to HTML.
    * Handles text
    * MathJax math
    * Pictures/images
    * Calls external code before rendering

    To maintain integrity, rendering from ``QTemplate`` to a ``QActual`` is
    only and ever done ONCE (at rendering time). Later, when the question is
    graded, or reloaded by the student, they will always see the same question.
    This is because questions may contain random values specific to the student
    so they must be rendered only once, including the correct solution, which
    often is dependent on the randomly selected values.

    Rendering order:
        1 Convert our internal representation to Markdown (or ReST)
        2 Pick random values for any variables in the question
        3 And/or evaluate any source code to obtain variables and solutions
        4 t_grading['answer'] string is run through rendering as well
        5 Render any variables using Jinja templates.
        6 Convert this markup to HTML.

    """
    def get_type(mcq_dict, keytype):
        """Gets the required key type(s) from the MCQ grading dictionary"""
        for key, value in mcq_dict.iteritems():
            if value[0] == keytype:
                yield value[1], key
    #----------------

    def render_mcq(qt):
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

        tplt = """<input type = "%s" name="%s" value="%s">%s</><br>"""

        lst = []
        name = generate_random_token(8)

        for (key, value) in get_type(qt.t_grading, keytype='key'):
            lst.append(tplt % (q_type, name, value, key))

        for (lure, value) in get_type(qt.t_grading, keytype='lure'):
            lst.append(tplt % (q_type, name, value, lure))

        random.shuffle(lst)
        for (final, value) in get_type(qt.t_grading, keytype='final'):
            lst.append(tplt % (q_type, name, value, final))

        return lst
    #----------------

    # 1. First convert strings to dictionaries:
    if isinstance(qt.t_grading, basestring):
        qt.t_grading = json.loads(qt.t_grading)
        qt.t_variables = json.loads(qt.t_variables)

    rndr = []

    if qt.q_type in ('mcq', 'tf', 'multi'):
        rndr.append(qt.t_question)
        rndr.append('- - -')
        rndr.extend(render_mcq(qt))


    # 2. Random variables, if required.
    vardict = {}
    if qt.t_variables:
        pass



    # 3. Evaluate source code

    # 4. Evalute the answer string???

    # 5. Now call Jinja to render any templates
    rndr_str = '\n'.join(rndr)

    # 6. Then call Markdown
    html = markdown.markdown(rndr_str)

    return html, json.dumps(vardict, separators=(',', ':'), sort_keys=True)


def auto_grade():
    """
    Auto-grades a question set.
    * Questions that cannot be auto-graded are distinctly shown as not
      graded yet
    """
    pass


#<form>
  #<fieldset>
   #<legend>Selecting elements</legend>
   #<p>
      #<label>Radio buttons</label>
      #<input type = "radio"
             #name = "radSize"
             #id = "sizeSmall"
             #value = "small"
             #checked = "checked" />
      #<label for = "sizeSmall">small</label>

      #<input type = "radio"
             #name = "radSize"
             #id = "sizeMed"
             #value = "medium" />
      #<label for = "sizeMed">medium</label>

      #<input type = "radio"
             #name = "radSize"
             #id = "sizeLarge"
             #value = "large" />
      #<label for = "sizeLarge">large</label>
    #</p>
  #</fieldset>
#</form>



#root = etree.Element("form")
#fs = etree.SubElement(root, "fieldset")
#legend
#s = etree.tostring(root, pretty_print=True)
