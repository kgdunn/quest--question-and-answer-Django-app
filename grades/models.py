from django.db import models

class Grade(models.Model):
    """
    The grade assigned to a particular ``QActual`` question.
    """
    grade_value = models.FloatField(default=0.0)
    # who graded this? Was it ``Quest Grader`` or a TA or the intstructor?
    given_by = models.ForeignKey('person.User')
    question = models.ForeignKey('question.QActual')
