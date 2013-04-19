from django.db import models

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

