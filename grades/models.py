from django.db import models

try:
    import simplejson as json
except ImportError:
    import json

class Grade(models.Model):
    """
    The grade assigned to a particular ``approved.QActual`` question.
    """
    # How much did the person score (can sometimes be negative, or in some
    # cases exceed the maximum)
    grade_value = models.FloatField(default=0.0)

    # who graded this? Was it ``Quest Grader`` or a TA or the intstructor?
    graded_by = models.ForeignKey('person.UserProfile')

    # Date/Time
    date_and_time = models.DateTimeField(auto_now=True)

    # If ``approved``, then the grade is used in the calculations.
    approved = models.BooleanField(default=False)

    # Reasons/description related to grading. e.g. could list deductions.
    # such as '-0.5 for per incorrect multiple choice' or 'too many significant
    # figures'
    # It is a JSON encoded list of strings.
    reason_description = models.CharField(blank=True, null=True,
                                          max_length=250)

    def save(self, *args, **kwargs):
        """ Override the model's saving function to do some changes """
        if isinstance(self.reason_description, list):
            self.reason_description = json.dumps(self.reason_description)
        super(Grade, self).save(*args, **kwargs)

    def __unicode__(self):

        return '[%f]: %s' % (self.grade_value, str(self.reason_description))

