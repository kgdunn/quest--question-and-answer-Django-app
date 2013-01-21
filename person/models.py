from django.contrib.auth.models import User
from django.db import models

# Our apps:
from utils import unique_slugify

class UserProfile(models.Model):
    # See https://docs.djangoproject.com/en/1.3/topics/auth/
    user = models.OneToOneField(User, unique=True, related_name="profile")

    # Slug field
    slug = models.SlugField(editable=False)

    # User's role
    role_choice = (
            ('Superuser', 'Superuser'),      # Django superuser
            ('Instructor', 'Instructor'),    # Highest level
            ('TA', 'TA'),                    # Next highest level
            ('Student', 'Student'),          # Lowest level
            ('Contributor', 'Contributor'),  # Just to acknowledge contribs
            ('Grader', 'Grader'),            # Auto-grader
    )
    role = models.CharField(choices=role_choice, max_length=20,
                            default='Student')

    student_number = models.CharField(max_length=20, blank=True)

    courses = models.ManyToManyField('course.Course')

    class Meta:
        verbose_name_plural = 'users'

    def save(self, *args, **kwargs):
        """ Override the model's saving function to create the slug """
        # http://docs.djangoproject.com/en/dev/topics/db/models/
                                          #overriding-predefined-model-methods
        unique_slugify(self, self.user.username, 'slug')

        # Call the "real" save() method.
        super(UserProfile, self).save(*args, **kwargs)

    def __unicode__(self):
        return 'Profile for: ' + self.user.username


class Token(models.Model):
    """
    Manages the unique sign-in tokens
    """
    user = models.ForeignKey(User)
    token_address = models.CharField(max_length=250)
    has_been_used = models.BooleanField(default=False)

    def __unicode__(self):
        return u'%s, %s, %s' % (str(self.has_been_used), str(self.user),
                                self.token_address)


class Timing(models.Model):
    """
    Manages the start and end times of various tests
    """
    user = models.ForeignKey(UserProfile)
    start_time = models.DateTimeField()
    final_time = models.DateTimeField()
    qset = models.ForeignKey('question.QSet')
    token = models.ForeignKey(Token)
    #is_valid = models.BooleanField(default=False)

    def __unicode__(self):
        return 'User %s -- Start: [%s] and Final [%s]' % \
                            (self.user.user.username,
                             self.start_time.strftime('%H:%M:%S on %d %h %Y'),
                             self.final_time.strftime('%H:%M:%S on %d %h %Y'))

