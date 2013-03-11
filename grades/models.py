from django.db import models

class Grade(models.Model):
    """
    The grade assigned to a particular ``approved.QActual`` question.
    """
    grade_value = models.FloatField(default=0.0)

    # who graded this? Was it ``Quest Grader`` or a TA or the intstructor?
    graded_by = models.ForeignKey('person.User')

    # Which question is being graded?
    question = models.ForeignKey('c.QActual')

    # Which QSet was this for?
    quiz = models.ForeignKey('question.QSet')

    # A field storing student comments
    feedback = models.TextField(blank=True, null=True)

    # If ``approved``, then the grade is used in the calculations.
    approved = models.BooleanField(default=False)

