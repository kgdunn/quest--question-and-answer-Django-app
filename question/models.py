"""
Handles the question templates, questions and question sets.

QTemplate: question templates hold the structure of the question, such as MCQ,
           short answer, or long answer questions. They contain placeholders
           so different values can be filled in.

QActual:   actual questions are derived from the QTemplate template. The
           placeholders are filled in with specific values. QActual questions
           are only used once, and they are unique to a user. There will
           be many of these in the database.
QSet:      defines a set of QTemplate questions from which the system can
           choose to make a set of QActual questions. You might have 16
           possible questions, but only want users to be randomly given
           N < 16 to answer. There is some flexibility in how questions are
           "randomly" assigned.

Some other terminology:
* Question: the question asked of the user
* Grading:  the internal representation of the answer (not shown, used for
            auto-grading)
* Solution: the solution displayed to the user
"""
# Django and Python imports
try:
    import simplejson as json
except ImportError:
    import json
from django.db import models
from django.core.urlresolvers import reverse
#from django.template.defaultfilters import slugify
from django.core.exceptions import ValidationError

# Our imports
from utils import unique_slugify

class QTemplate(models.Model):
    """
    The template for a question.
    """
    question_type = (
                ('tf',       'True/False question'),
                ('mcq',      'Multiple choice question'),
                ('multi',    'Multi-select'),  # Like MCQ, but multiple options
                ('short',    'Short answer question'),
                ('long',     'Long answer question'),
                ('numeric',  'Numeric answer (with specified sensitivity)'),
                ('fib',      'Fill in the blanks'),
                ('multipart','Multipart questions'),
    )
    # e.g. "The misbehaving clock", if given explictly, else it is the first
    # few characters of the question itself.
    name = models.CharField(max_length=250)

    q_type = models.CharField(max_length=10, choices=question_type)
    contributor = models.ForeignKey('person.UserProfile', blank=True)
    tags = models.ManyToManyField('tagging.Tag', blank=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    max_grade = models.PositiveSmallIntegerField()

    # Can students provide feedback on this question
    enable_feedback = models.BooleanField(default=True)

    # When uploaded
    when_uploaded = models.DateTimeField(auto_now_add=True, blank=True,
                                         null=True)

    # The question template
    t_question = models.TextField()
    # The solution template
    t_solution = models.TextField(blank=True, null=True)
    # The grading dictionary (string-representation)
    t_grading = models.TextField()
    # Variables used in the templates (``t_question`` and ``t_solution``)
    t_variables = models.TextField(blank=True, null=True)
    # Source code used to evaluate any variables and grading responses
    t_code = models.TextField(blank=True, null=True)

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

        if isinstance(self.t_variables, dict):
            self.t_variables = json.dumps(self.t_variables, sort_keys=True)
        if isinstance(self.t_grading, (dict, basestring)):
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
    announcement = models.TextField(blank=True)

    # Should questions be randomly chosen from a set of questions?
    # If False, then all questions in ``include`` will be asked.
    #
    # If True, then the questions will be randomly selected using rules
    # based on ``min_total``, ``max_total``, ``min_num`` and ``max_num`` to
    # guide the random selection
    random_choice = models.BooleanField(default=True,
                                        help_text = ('Randomly choose '
                                        'questions for the users'))
    min_total = models.FloatField(verbose_name='Total minimum grade',
                                  help_text = ('Minimum total grades allowed '
                                               'in set'), default=0.0)
    max_total = models.FloatField(verbose_name='Total maximum grade',
                                  help_text = ('Maximum total grades allowed '
                                               'in set'), default=0.0)
    min_num = models.PositiveIntegerField(verbose_name=('Fewest number of '
                                                         'questions in set'),
                                          default=0)
    max_num = models.PositiveIntegerField(verbose_name=('Most number of '
                                                         'questions in set'),
                                          default=0)

    min_difficulty = models.FloatField(verbose_name='Min average difficulty',
              help_text = ('Minimum average difficulty across all questions'),
              default=0.0, blank=True)

    max_difficulty = models.FloatField(verbose_name='Max average difficulty',
              help_text = ('Maximum average difficulty across all questions'),
              default=0.0, blank=True)

    # Many-to-many? A QTemplate can be part of multiple QSet objects, and a
    #               QSet has multiple QTemplate objects.
    # This lists which questions are included, and their relative weight.
    include = models.ManyToManyField(QTemplate, through="Inclusion")

    # Certain question templates might be required to always be present
    # Use the ``related_name`` because there are two M2M relationships here
    #weights_q = models.ManyToManyField(QTemplate,

    # Which course is this qset used in
    course = models.ForeignKey('course.Course')

    # When are questions first available and finally available for answering?
    ans_time_start = models.DateTimeField(blank=True, null=True)
    ans_time_final = models.DateTimeField(blank=True, null=True)

    # Maximum test duration, e.g. 1 hour is "01:00:00". If 00:00, then allow the
    # test to be completed anytime between ``ans_time_start`` and
    # ``ans_time_final``.
    max_duration = models.TimeField(default="00:00:00")

    # Intended to be used later to allow super-users to preview tests before
    # they are made available to regular student users
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        """ Override  model's saving function to do some checks """
        # Call the "real" save() method.

        # http://docs.djangoproject.com/en/dev/topics/db/models/
                                            #overriding-predefined-model-methods
        unique_slugify(self, '%s %s %s' % (self.name, self.course.code,
                                           self.course.year), 'slug')

        # happens if the slug is totally unicode characters
        if len(self.slug) == 0:
            raise ValidationError('QSet slug contains invalid characters')

        if self.min_num > self.max_num:
            raise ValidationError(('Minimum number of questions must be '
                                    'smaller or equal to maximum number.'))

        if self.min_total > self.max_total:
            raise ValidationError(('Minimum total must be '
                                   'smaller or equal than the maximum total.'))

        if self.min_difficulty > self.max_difficulty:
            raise ValidationError(('Minimum difficulty must be smaller '
                                   'or equal to the maximum difficulty.'))

        # Call the "real" save() method.
        super(QSet, self).save(*args, **kwargs)


    def __unicode__(self):
        return '%s [%s]' % (self.name, self.course.name)


class Inclusion(models.Model):
    """
    Captures relative inclusion weightings for questions in a QSet
         0: never include it
    1 or 2: about 25% of the questions will come from these weights
    3 or 4: about 75% of the questions will come from these weights
         5: these questions will always be included; once included the
            remaining questions will be allocated as described above, i.e.
            the 25% or 75% refer to the remaining space **after** the level 5
            questions have been included.

         7: these are bonus questions; they will always be added to the list,
            and may cause the difficulty and number of questions to exceed
            their respective constraints (but that's why they are bonus).

    Note however, that if all level 5, 4, and 3 questions are used up, then
    we will fill the quiz with level 1 and 2 questions, to get to the desired
    number of grades and difficulty. So the 25/75 ratio won't always be obeyed,
    but they are good guides for the case when there are excess questions
    available.
    """
    qtemplate = models.ForeignKey(QTemplate)
    qset = models.ForeignKey(QSet)
    weight = models.PositiveSmallIntegerField(default=1, help_text=(' '
        '0: never include; 2: 25% inclusion rate; 4: 75% inclusion;'
        '5: definitely include; 7=bonus credit'))

    def save(self, *args, **kwargs):
        """ Override  model's saving function to do some checks """

        previous = Inclusion.objects.filter(qset=self.qset).\
                       filter(qtemplate=self.qtemplate)
        if previous:
            raise ValidationError(('This question template is already '
                                    'included in this question set'))

        super(Inclusion, self).save(*args, **kwargs)


    def __unicode__(self):
        return 'Question [id=%d] in QSet "%s"' % (self.qtemplate.id,
                                                  self.qset)


class QActual(models.Model):
    """
    The actual question asked to the user. There are many many of these in
    the database.
    """
    # Question origin
    qtemplate = models.ForeignKey(QTemplate)

    # Which question set was this question used in?
    # Only allow/expect blanks with Previews and unit tests
    qset = models.ForeignKey(QSet, null=True, blank=True)

    # Who is answering this question?
    user = models.ForeignKey('person.UserProfile')

    # HTML formatted code that was displayed to the user, so we have an
    # accurate reflection of the question
    as_displayed = models.TextField(blank=True)

    # HTML solution that's to be displayed after the question period is over
    html_solution = models.TextField(blank=True)

    # The variables dictionary used to render the template is also saved
    # To be compatible with our template rendering engine, the
    # variable names in the dict must be strings: [a-zA-Z_][a-zA-Z0-9_]*
    var_dict = models.TextField(blank=True)

    # The user's answer (may be intermediate still)
    given_answer = models.TextField(blank=True)
    # * list of strings: ['tf', 'mcq', 'multi']    <- refers to QTemplate.question_type
    # * string: 'short', 'long', 'numeric'         <- string only
    # * dict: {'fib': '....'; 'multipart': '...'}  <- dict of strings

    # A copy of the ``QTemplate.t_grading`` field, but customized for this
    # user. Grading keys for the same question can vary from student to
    # student, depending on their specific question values
    grading_answer = models.TextField(blank=True)

    # The user's comments on the question; user uploaded material
    user_comments = models.TextField(blank=True)
    #user_material = models.FileField(upload_to='user-uploads/%Y/%m/%d',
    #                                  blank=True)

    # Feedback from the student based on the grading. (How does this differ
    # from the above field?)
    feedback = models.TextField(blank=True, null=True)

    # NOTE: it is a conscious decision not to assign grades to the ``QActual``
    #       objects. We rather assign grades in a ``grades.Grade`` object;
    #       these are smaller and we can deal with grading as a separate
    #       event.
    grade = models.ForeignKey('grades.Grade', blank=True, null=True)

    # Helps to relate the item to webserver logs, traceability, etc
    last_edit = models.DateTimeField(auto_now=True, blank=True, null=True)

    # Has the question been submitted yet? True: used actively clicked the
    # submit button; ``False``: XHR stored answer.
    is_submitted = models.BooleanField(default=False)

    # Links to the previous and next question in the series
    next_q = models.ForeignKey('self', blank=True, null=True, editable=False,
                               related_name='next_question')
    prev_q = models.ForeignKey('self', blank=True, null=True, editable=False,
                               related_name='prev_question')

    def __unicode__(self):
        if self.qset:
            return u'%s, for user "%s", in %s of course "%s"' % (
                self.qtemplate.name,
                self.user.user.username,
                self.qset.name,
                self.qset.course)
        else:
            return u'%s, for user "%s"' % (
                            self.qtemplate.name,
                            self.user.user.username)

    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some changes """
        if isinstance(self.var_dict, dict):
            self.var_dict = json.dumps(self.var_dict, sort_keys=True)

        #if self.user_material:
        # TODO(KGD): validate the user's upload is OK

        super(QActual, self).save(*args, **kwargs)

    def qtemplate_id(self, instance):
            return instance.qtemplate.id
