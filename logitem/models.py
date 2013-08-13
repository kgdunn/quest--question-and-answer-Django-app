from django.db import models
from person.models import UserProfile

#class BrowserID(models.Model):
    #""" Collects information about the user so we can track and enhance
    #the experience in the future"""
    ## https://panopticlick.eff.org/resources/fetch_whorls.js
    #user_agent = models.CharField(max_length=200, blank=True) # HTTP_USER_AGENT
    #http_accept = models.CharField(max_length=100, blank=True)# HTTP_ACCEPT
    #resolution = models.CommaSeparatedIntegerField(max_length=50, blank=True)
    #timezone = models.SmallIntegerField(blank=True)


class PageHit(models.Model):
    """ Records each hit (page view) of an item

    The only requirement is that the item must have an integer primary key.
    """
    # browser's user agent
    ua_string = models.CharField(max_length=255)

    # profile of the browser
    profile = models.CharField(max_length=32, null=True, blank=True)
    ip_address = models.IPAddressField()
    datetime = models.DateTimeField(auto_now=True)
    item = models.CharField(max_length=50)
    user_id = models.IntegerField()
    item_pk = models.IntegerField()
    extra_info = models.CharField(max_length=512, null=True, blank=True)


class Profile(models.Model):
    """
    Creates the MD5 hash of the user profile
    """
    ua_string = models.CharField(max_length=255)
    software = models.CharField(max_length=5000)
    os = models.CharField(max_length=50)
    display = models.CharField(max_length=255)
    hashid = models.CharField(max_length=32)
    datetime = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return self.hashid



    #def user_slug(self):
        #user = UserProfile.objects.filter(id=self.user_id)
        #if user:
            #return user.slug
        #else:
            #return 'User not found'
    #user_slug.short_description = "User's slug"


    #def most_viewed(self, field):
        #""" Most viewed in terms of a certain item.
        #"""
        #return PageHit.objects.filter(item=field)\
                            #.annotate(score=models.Count('revision'))\
                            #.order_by('-score', 'username')


    ## Tracking on the question
    ## ---------------------------
    ## TODO When was the question displayed in the browser [comma-separated list]
    #times_displayed = models.ManyToManyField(DateTimes,
                                             #related_name='displayed')

    ## When was the question answered by the users [comma-separated list]
    #times_answered = models.ManyToManyField(DateTimes,
                                            #related_name='answered')

    ## Browser ID
    #browsers = models.ManyToManyField(BrowserID)
