# Python and Django imports
import re
import json
import random
import logging

# 3rd party imports
import markdown
import numpy as np

# Our imports
from question.models import (QTemplate, QSet, QActual)
from person.models import (UserProfile,)
from tagging.views import get_and_create_tags
from utils import generate_random_token
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

    # Process the variables
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
                pass

        sd.pop('variables')


    # Final checks before returning
    if not sd.has_key('name'):
        sd['name'] = t_question

    sd['t_question'] = t_question
    sd['t_solution'] = t_solution
    sd['t_grading'] = t_grading
    sd['t_variables'] = var_dict

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
        n_questions = len(qts)

        for idx, qt in enumerate(qts):
            html, var_dict = render(qt)

            prev_q = next_q = None
            if idx == 0:
                if n_questions > 1:
                    next_q = qts[1]
            elif idx == n_questions-1:
                if n_questions > 1:
                    prev_q = qts[idx-1]

            qa = QActual.objects.create(qtemplate=qt, qset=qset[0],
                                        user=user, as_displayed=html,
                                        var_dict=var_dict,
                                        next_q=next_q, prev_q=prev_q)
            print(qa)

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
    var_dict = {}
    if qt.t_variables:
        var_dict = create_random_variables(qt.t_variables)



    # 3. Evaluate source code

    # 4. Evalute the answer string???

    # 5. Now call Jinja to render any templates
    rndr_str = '\n'.join(rndr)

    # 6. Then call Markdown
    html = markdown.markdown(rndr_str)

    return html, json.dumps(var_dict, separators=(',', ':'), sort_keys=True)


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
        if type(val[0]) in (list,):
            spec = val[0]
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
            rnd_val = np.random.normal(loc=(hi-lo)/2.0, scale=(hi-lo)/6.0)

        temp = rnd_val * (hi - lo)
        # Randomly round ``temp`` down or round up:
        # e.g. [60, 100, 8] and if rnd_val = 0.25, then temp = 0.25*40 = 10
        #      we can legimately choose 68 or 76 to round towards. Make this
        #      a random decision, so we are not biased
        if np.random.rand() < 0.5:
            temp = np.floor(temp/(step+0.)) * step + lo
        else:
            temp = np.ceil(temp/(step+0.)) * step + lo

        if v_type == 'int':
            var_dict[key][1] = int(temp)
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



#from django import template
#from django.template.defaultfilters import stringfilter
#register = template.Library()

#g = """{% load quest_render_tags %} x + y = {% evaluate %}\n a=x+y\n b=a+4\n return b {% endeval %}"""
#g = """{% load quest_render_tags %} x + y = {% quick_eval "x/y" 5 %}"""
#g = """{% load quest_render_tags %} x + y = {% quick_eval "x*ln(y)" 5 %}"""
#from django.template import Context, Template
#t = Template(g)
#c = Context({'x':4, 'y':20})
#r = t.render(c)
#print(r)
