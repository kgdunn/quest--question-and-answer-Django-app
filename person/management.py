# Setting up the superuser correctly after ``syncdb``. That's because we have
# subclassed the django.contrib.auth.models.User class, but ``syncdb`` doesn't
# create an entry in the ``UserProfile`` database table.

# Code from  Marty Alchin's book: Pro Django, page 82.
from django.db.models import signals

def validate_superuser(app, created_models, verbosity, **kwargs):
    app_label = app.__name__.split('.')[-2]
    #app_name = __name__.split('.')[-2]
    #app_models = [m for m in created_models if m._meta.app_label == app_label]
    #print(app_label, app_name, app_models)

    if app_label == 'auth':
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured
        from django.db.models import get_model
        from django.contrib.auth.models import User
        user_class = get_model(*settings.AUTH_PROFILE_MODULE.split('.', 2))
        if not user_class:
            raise ImproperlyConfigured('Could not get custom user model')

        users = User.objects.all()
        if len(users)==1 and users[0].is_superuser:
            print('Validating superuser in the subclassed user table')

            user = user_class.objects.create(user=users[0])
            user.role = 'Superuser'
            user.save()

        from django.core import mail
        if len(users)==0 and hasattr(mail, 'outbox'):
            # We are in testing mode. Create a superuser for testing purposes.
            user = User.objects.create(username='__TESTING_SU__',
                                       is_superuser=True)
            user_prof = user_class.objects.create(user=user)
            user_prof.role = 'Superuser'
            user_prof.save()

        # This user SHOULD NEVER create Templates and QActual objects that
        # are intended to be retained/used for the long term.
        # This user is used to create temporary objects, which will be deleted
        # periodically AND automatically, without prompt, from the database.
        #if len(User.objects.filter(username='quest-grader-previewer')) == 0:
            ## Only create this user if it doesn't exist
            #auto_user = User.objects.create(username='quest-grader-previewer',
                                    #email='quest.grader.previewer@example.com',
                                    #is_active=False)
            #auser = user_class.objects.create(user=auto_user)
            #auser.role = 'Grader'
            #auser.save()



    # While we are here (and this isn't user related) check the name of
    # the site. If it is "example.com", change it to actual name
    if app_label == 'sites':
        from django.contrib.sites.models import Site
        from django.conf import settings
        site = Site.objects.get_current()
        if site.name == 'example.com':
            site.name = settings.QUEST['SITE_NAME']
            site.domain = settings.QUEST['FULL_DOMAIN_NO_HTTP']
            site.save()



signals.post_syncdb.connect(validate_superuser)
