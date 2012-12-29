"""
General administrative models.
"""
from django.db import models

class Course(models.Model):
    """
    Define course related items.
    """
    # Full course name
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)  # shorter course code

    def __unicode__(self):
        return self.code