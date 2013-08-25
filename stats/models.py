from django.db import models

from person.models import UserProfile

class PageHit(models.Model):
    """ Records each hit (page view) of an item

    The only requirement is that the item must have an integer primary key.
    """
    # browser's user agent
    ua_string = models.CharField(max_length=255, null=True, blank=True)

    # profile of the browser
    profile = models.CharField(max_length=32, null=True, blank=True)
    ip_address = models.IPAddressField()
    datetime = models.DateTimeField(auto_now=True)
    item = models.CharField(max_length=50)

    item_pk = models.IntegerField()
    extra_info = models.CharField(max_length=512, null=True, blank=True)

    # Also record the user_id, so we can sort based on it in the Admin interface
    user_id = models.IntegerField()
    userp = models.ForeignKey(UserProfile, null=True, blank=True, default=None)

    def __unicode__(self):
        if self.userp:
            return "%s [%s]" % (self.item, self.userp.slug)
        else:
            return self.item

class Profile(models.Model):
    """
    Creates the MD5 hash of the user profile
    """
    # The user's user agent string
    ua_string = models.CharField(max_length=255)

    # The user's browser plugins
    software = models.CharField(max_length=10000)

    # The user's operating system
    os = models.CharField(max_length=50)

    # The user's display settings
    display = models.CharField(max_length=255)

    # A hash created from the above 4 profiling objects
    hashid = models.CharField(max_length=32)
    datetime = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return self.hashid

    # Tracking on the question
    # ---------------------------
    # TODO When was the question displayed in the browser [comma-separated list]
    #      When was the question answered by the users [comma-separated list]
    #      times_answered

class TimerStart(models.Model):
    """General timinig statistics about the site usage are summarized here."""
    event_type = (
        ('login', 'login'),
        ('show-all-course-quests', 'show-all-course-quests'),
        ('start-a-quest-session', 'start-a-quest-session'),
        ('review-a-quest-session', 'start-a-quest-session'),
        ('review-a-quest-question-during', 'review-a-quest-question-during'),
        ('review-a-quest-question-post', 'review-a-quest-question-post'),
        ('start-question', 'start-question'),
        ('modify-answer', 'modify-answer'),
                  )
    event = models.CharField(max_length=80, choices=event_type)
    time = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(UserProfile)
    referrer = models.CharField(max_length=511, blank=True, null=True)
    other_info = models.CharField(max_length=5000, blank=True, null=True,
                                  default=None)
    # Get if from: request.session.get('profile', None)
    profile = models.ForeignKey(Profile, null=True, blank=True)
    item_pk = models.IntegerField()      # Store the referencing item's PK
    item_type = models.CharField(max_length=80, null=True, blank=True)

    def __unicode__(self):
        return '%s [%s]' % (self.event, self.user.slug)



