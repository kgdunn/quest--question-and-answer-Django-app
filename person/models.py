from django.contrib.auth.models import User
from django.db import models
from django.core.exceptions import ValidationError

# Our apps:
from utils import unique_slugify

class Group(models.Model):
    """
    Users (below) may belong to a group.
    """
    name = models.CharField(verbose_name='Group name',
                           max_length=50,
                           help_text='Users might belong to a group',
                           )

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ['name', ]



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

    group = models.ForeignKey(Group, blank=True, null=True)

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
        return self.slug

    def get_peers(self):
        if self.group:
            userP = list(UserProfile.objects.filter(group=self.group))
            userP.remove(self)
            out = []
            for item in userP:
                out.append(('%s %s' % (item.user.first_name,
                                      item.user.last_name), item.user.username))

            return(out)

        else:
            return []


class Token(models.Model):
    """
    Manages the unique sign-in tokens. Tokens are purely for authentication of
    the user. They are never used to authorize access to any type of info.
    """
    user = models.ForeignKey(User)
    token_address = models.CharField(max_length=250)
    has_been_used = models.BooleanField(default=False)

    def __unicode__(self):
        return u'%s, %s, %s' % (str(self.has_been_used), str(self.user),
                                self.token_address)


class Timing(models.Model):
    """
    Manages the start and end times of various tests. This is the primary
    authorization mechanism.
    Timing objects are not created when the QSet requested is outside of its
    start and end time. e.g. when the user is signing in to review answers
    from prior QSets or for other courses.
    """
    user = models.ForeignKey(UserProfile)
    start_time = models.DateTimeField()
    final_time = models.DateTimeField()
    qset = models.ForeignKey('question.QSet')
    token = models.ForeignKey(Token)

    def __unicode__(self):
        return 'User %s -- Start: [%s] and Final [%s]' % \
                            (self.user.slug,
                             self.start_time.strftime('%H:%M:%S on %d %h %Y'),
                             self.final_time.strftime('%H:%M:%S on %d %h %Y'))

    def save(self, *args, **kwargs):
        if self.start_time >= self.final_time:
            raise ValidationError('Start time must be earlier than end time.')
        if self.start_time < self.qset.ans_time_start:
            raise ValidationError('Start time must be later than QSet start time.')
        if self.start_time > self.qset.ans_time_final:
            raise ValidationError('Cannot start test after QSet final time.')
        if self.final_time < self.qset.ans_time_start:
            raise ValidationError('Cannot end test before QSet start time.')
        if self.final_time > self.qset.ans_time_final:
            raise ValidationError('Cannot end test after QSet final time.')
        super(Timing, self).save(*args, **kwargs)
