# Python and Django imports
import re

# Our imports
from models import (QTemplate, QSet, QActual)
from person.models import UserProfile
from tagging.views import get_and_create_tags

# TODO(KGD): allow these to be case-insenstive later on
CONTRIB_RE = re.compile(r'^Contributor:(\s*)(.*)$')
TAGS_RE = re.compile(r'^Tags:(\s*)(.*)$')
DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(.*)$')
GRADES_RE = re.compile(r'^Grade:(\s*)(.*)$')
FEEDBACK_RE = re.compile(r'^Feedback:(\s*)(.*)$')

LURE_RE = re.compile(r'^\&(\s*)(\S*)$')
KEY_RE = re.compile(r'^\^(\s*)(\S*)$')
FINAL_RE = re.compile(r'^\&(\s*)(\S*)$')

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
        t_solution = '<function>'
        t_grading = '<function>'
    else:
        t_solution = dict()
        t_solution['key'] = ''
        t_solution['lures'] = []
        t_solution['final'] = ''

        t_grading = {}
        for line in text:
            if line.startswith('%'):
                section_name = 'final'
                final = FINAL_RE.match(line).group(2)
                t_solution[section_name] = final
                continue

            elif line.startswith('^'):
                section_name = 'key'
                key = KEY_RE.match(line).group(2)
                t_solution[section_name] = key
                continue

            elif line.startswith('&'):
                section_name = 'lures'
                lure = LURE_RE.match(line).group(2)
                t_solution['lures'].append(lure)
                continue

            if isinstance(t_solution[section_name], list):
                t_solution[section_name].append(line)
            else:
                t_solution[section_name] += '\n' + line


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
        #tag_intermediate = models.InterestCreation(user=user.profile,
        #                                           tag=tag)
        #tag_intermediate.save()
        qtemplate.tags.add(tag)

    return qtemplate

def generate_questions():
    """
    1. Generates the questions from the question sets, rendering templates
    2. Emails students in the class the link to sign in and start answering
    """

    # Remember to copy over the rendered HTML to the question and the q_variables
    # dict used in the template
    pass


def render():
    """
    Renders templates to HTML.
    * Handle text
    * MathJax math
    * Pictures/images
    * Calls external code before rendering
    """
    pass


def auto_grade():
    """
    Auto-grades a question set.
    * Questions that cannot be auto-graded are distinctly shown as not
      graded yet
    """
    pass

