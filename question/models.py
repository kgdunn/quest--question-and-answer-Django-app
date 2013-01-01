"""
Handles the question templates, questions and question sets.

QTemplate: question templates hold the structure of the question, such as MCQ,
           short answer, or long answer questions. They contain placeholders
           so different values can be filled in.

QActual:   actual questions are derived from the QTemplate template. The
           placeholders are filled in with specific values. QActual questions
           are only used once, and they are unique to a student. There will
           be many of these in the database.

QSet:      defines a set of QTemplate questions from which the system can
           choose to make a set of QActual questions. You might have 16
           possible questions, but only want students to be randomly given
           N < 16 to answer. There is some flexibility in how questions are
           "randomly" assigned.

Some other terminology:
* Question: the question asked of the student
* Grading:  the internal representation of the answer (not shown, used for
            auto-grading)
* Solution: the solution displayed to the student
"""
# Django and Python imports
try:
    import simplejson as json
except ImportError:
    import json
from django.db import models
from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError

class DateTimes(models.Model):
    """ Date and times something was accessed or created."""
    dt = models.DateTimeField()

class IPAddresses(models.Model):
    """ IP addresses used to access material. """
    ip = models.GenericIPAddressField(blank=True)

class BrowserID(models.Model):
    """ Collects information about the user so we can track and enhance
    the experience in the future"""
    # https://panopticlick.eff.org/resources/fetch_whorls.js
    user_agent = models.CharField(max_length=200, blank=True) # HTTP_USER_AGENT
    http_accept = models.CharField(max_length=100, blank=True)# HTTP_ACCEPT
    resolution = models.CommaSeparatedIntegerField(max_length=50, blank=True)
    timezone = models.SmallIntegerField(blank=True)



class QTemplate(models.Model):
    """
    The template for a question.
    """
    question_type = (
                ('mcq',      'Multiple choice question (including True/False'),
                ('short',    'Short answer question'),
                ('long',     'Long answer question'),
                ('multi',    'Multi-select'),  # Like MCQ, but multiple options
                ('fib',      'Fill in the blanks'),
                ('numeric',  'Numeric answer (with specified sensitivity)'),
                ('multipart','Multipart questions'),
    )
    name = models.CharField(max_length=250)     # e.g. "The misbehaving clock"
    q_type = models.CharField(max_length=10, choices=question_type)
    contributor = models.ForeignKey('person.UserProfile', blank=True)
    tags = models.ManyToManyField('tagging.Tag', blank=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    max_grade = models.PositiveSmallIntegerField()

    # Can students provide feedback on this question
    enable_feedback = models.BooleanField(default=True)

    # The question template
    t_question = models.TextField()
    # The solution template
    t_solution = models.TextField(blank=True, null=True)
    # The grading dictionary (string-representation)
    t_grading = models.TextField()
    # Variables used in the templates (``t_question`` and ``t_solution``)
    t_variables = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some checks """
        # http://docs.djangoproject.com/en/dev/topics/db/models/
                                          #overriding-predefined-model-methods

        # Clean up the lures/distractors from empty items (blank lines)
        #if self.q_type in ('mcq', 'tf', 'multi'):
        #    if self.t_grading.has_key('lures'):
        #        self.t_grading['lures'] =  [lure for lure in
        #                                     self.t_grading['lures'] if
        #                                     lure.strip()]

        self.t_variables = json.dumps(self.t_variables, sort_keys=True)
        self.t_grading = json.dumps(self.t_grading, sort_keys=True)
        self.max_grade = float(self.max_grade)
        self.difficulty = int(self.difficulty)
        self.difficulty = min(self.difficulty, 9)

        # Call the "real" save() method.
        super(QTemplate, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.name


class QSet(models.Model):
    """
    Manages sets of questions (question set)
    """
    name = models.CharField(max_length=250)    # e.g. "Week 1"
    slug = models.SlugField(editable=False)

    # Should questions be randomly chosen from a set of questions?
    # If False, then all questions in ``qtemplates`` will be asked.
    # If True, then the questions will be randomly selected using rules
    #      in ``min_total``, ``max_total``, ``min_num`` and ``max_num`` to
    #      guide the random selection
    random_choice = models.BooleanField(default=True,
                                        help_text = ('Randomly choose '
                                        'questions for the students'))
    min_total = models.FloatField(verbose_name='Total minimum grade',
                                  help_text = ('Minimum total grades allowed '
                                               'in set'))
    max_total = models.FloatField(verbose_name='Total maximum grade',
                                  help_text = ('Maximum total grades allowed '
                                               'in set'))
    min_num = models.PositiveIntegerField(verbose_name=('Fewest number of '
                                                         'questions in set'))
    max_num = models.PositiveIntegerField(verbose_name=('Most number of '
                                                         'questions in set'))

    # Many-to-many? A QTemplate can be part of multiple QSet objects, and a
    #               QSet has multiple QTemplate objects:
    qtemplates = models.ManyToManyField(QTemplate)

    # Certain question templates might be required to always be present
    # Use the ``related_name`` because there are two M2M relationships here
    forced_q = models.ManyToManyField(QTemplate, related_name='forced',
                                      blank=True)

    bonus_q = models.ManyToManyField(QTemplate, related_name='bonus',
                                     blank=True, null=True)

    course = models.ForeignKey('course.Course')

    # When are questions first available and finally available for answering?
    ans_time_start = models.DateTimeField(blank=True, null=True)
    ans_time_final = models.DateTimeField(blank=True, null=True)

    # Maximum test duration. If 0, then allow the test to be completed anytime
    # up till ``ans_time_final``.
    max_duration = models.TimeField(default="00:00")

    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        """ Override  model's saving function to do some checks """
        # Call the "real" save() method.

        slug = slugify(self.name)

        # happens if the slug is totally unicode characters
        if len(slug) == 0:
            raise ValidationError('QSet slug contains invalid characters')

        if QSet.objects.filter(slug=slug):
            return
        else:
            # Call the "real" save() method.
            self.slug = slug
            super(QSet, self).save(*args, **kwargs)


    def __unicode__(self):
        return u'%s [%s]' % (self.name, self.course.name)


class QActual(models.Model):
    """
    The actual question asked to the student. There are many many of these in
    the database.
    """
    # Question origin
    qtemplate = models.ForeignKey(QTemplate)

    # Which question set was this question used in?
    qset = models.ForeignKey(QSet)

    # Who is answering this question?
    user = models.ForeignKey('person.UserProfile')

    # HTML formatted code that was displayed to the user, so we have an
    # accurate reflection of the question
    as_displayed = models.TextField(blank=True)
    # The variables dictionary used to render the template is also saved
    # To be compatible with our template rendering engine (Jinja2), the
    # variable names in the dict must be strings: [a-zA-Z_][a-zA-Z0-9_]*
    var_dict = models.TextField(blank=True)

    # The student's answer
    given_answer = models.TextField(blank=True)

    # NOTE: it is a conscious decision not to assign grades to the ``QActual``
    #       objects. We rather assign grades in a ``grades.Grade`` object;
    #       these are smaller and we can deal with grading as a separate
    #       event.


    # Tracking on the question
    # ---------------------------
    # When was the question displayed in the browser [comma-separated list]
    times_displayed = models.ManyToManyField(DateTimes,
                                             related_name='displayed')

    # When was the question answered by the students [comma-separated list]
    times_answered = models.ManyToManyField(DateTimes,
                                            related_name='answered')

    # Browser ID
    browsers = models.ManyToManyField(BrowserID)



    def __unicode__(self):
        return u'%s [for %s]' % (self.qtemplate.name,
                                 self.user.user.username)



