import re
from orderedmultidict import omdict

class ParseError(Exception): pass

def parse_question_text(text):
    """
    Parses a question's template text to create our internal question
    representation.

    Rules:
    #. First line must be "Type:__________" where the missing part is one of
       the valid question types
    """
    TYPE_RE = re.compile(r'^Type:(\s*)(\S*)$')
    CONTRIB_RE = re.compile(r'^Contributor:(\s*)(\S*)$')
    TAGS_RE = re.compile(r'^Tags:(\s*)(\S*)$')
    DIFFICULTY_RE = re.compile(r'^Difficulty:(\s*)(\S*)$')
    POINTS_RE = re.compile(r'^Points:(\s*)(\S*)$')
    LURE_RE = re.compile(r'^\&(\s*)(\S*)$')
    KEY_RE = re.compile(r'^\^(\s*)(\S*)$')
    FINAL_RE = re.compile(r'^\&(\s*)(\S*)$')

    # Force it into a list of strings.
    if isinstance(text, basestring):
        text = text.split('\n')

    q_type = None
    name = None
    contrib = 1
    tags = ''
    difficulty = 1
    max_points = 1
    while text[0].strip() != '--':
        line = text[0].strip()

        if TYPE_RE.match(line):
            q_type = TYPE_RE.match(line).group(2)

        if CONTRIB_RE.match(line):
            contrib = CONTRIB_RE.match(line).group(2)

        if TAGS_RE.match(line):
            tags = TAGS_RE.match(line).group(2)

        if DIFFICULTY_RE.match(line):
            difficulty = DIFFICULTY_RE.match(line).group(2)

        if POINTS_RE.match(line):
            max_points = POINTS_RE.match(line).group(2)

        text.pop(0)

    # This item is mandatory
    if not q_type:
        raise ParseError('Question type not specified.')

    # Instruction must follow now
    text.pop(0)
    instruction = []
    while text[0].strip() != '--':
        instruction.append(text[0].strip())
        text.pop(0)

    text.pop(0)
    t_question = ''.join(instruction)

    # Handles the case of the """--\n--\n""" where we specify the solution in
    # terms of a function.
    if text[0].strip() == '--':
        t_solution = '<function>'
    else:
        t_solution = omdict()
        while text[0].strip() != '--':
            soln = text[0].strip()
            if soln.startswith('%'):
                # Final multiple choice option
                final = FINAL_RE.match(soln).group(2)
                t_solution.add('final', final)

            elif soln.startswith('^'):
                # Correct option
                key = KEY_RE.match(soln).group(2)
                t_solution.add('key', key)

            elif soln.startswith('&'):
                # Lure or distractor answer
                lure = LURE_RE.match(soln).group(2)
                t_solution.add('lure', lure)

            else:
                raise ParseError(('A line [%s] in an MCQ/TF/Multi question '
                                  'must start with either ^, & or %'))


            # end if-elif
            text.pop(0)


    # Final checks before returning
    if name is None:
        name = t_question

    return (q_type, name, contrib, tags, difficulty, max_points,
            t_question, t_solution, t_grading)



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

