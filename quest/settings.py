# Project dependancies
# ----------------------
# easy_install -U django       <--- version 1.7.1 used during development
# easy_install -U simplejson   <--- version 3.6.5
# easy_install -U psychopg2    <--- version 2.5.1
# easy_install -U python-magic <--- version 0.4.6

# easy_install -U markdown   <--- version 2.5.2
# easy_install -U numpy      <--- version 1.6.2
# easy_install -U pygments   <--- version 2.0.1
# easy_install -U pil        <--- version 1.1.7  (for ImageField) http://stackoverflow.com/questions/19532125/cant-install-pil-after-mac-os-x-10-9


import os
import django.conf.global_settings as DEFAULT_SETTINGS
DEBUG = True
TESTING = False  # Set to False during unit test to previous sending email
#TEMPLATE_DEBUG = DEBUG
TEMPLATE_DEBUG = True

ALLOWED_HOSTS = ['*']

ADMINS = (
     ('Kevin Dunn', 'kevin.dunn@mcmaster.ca'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'database.db',                  # Or path to database file if using sqlite3.
        'USER': '',                      # Not used with sqlite3.
        'PASSWORD': '',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'America/Toronto'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = False

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
if DEBUG:
    MEDIA_ROOT = os.path.dirname(__file__) + os.sep + 'media' + os.sep
else:
    # For production: you'll want to copy the <base>/media/* files to your
    # static location and modify this path to match your server.
    MEDIA_ROOT = '<your path here>'

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '/media/'

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = ''

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/media/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'u317^!#!@v9$wsfs7uarlox$(voaj(t8_rxj)_t7o!00&amp;yc81('

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.BrokenLinkEmailsMiddleware',  # <-- add for newer Django version; must go first

    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',  # <--- add this


    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

import re
IGNORABLE_404_URLS = (
    re.compile(r'\.(php|cgi)$'),
    re.compile(r'^/phpmyadmin/'),
)


AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.RemoteUserBackend',
    'django.contrib.auth.backends.ModelBackend',
)
LOGIN_URL = '/'

ROOT_URLCONF = 'quest.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'quest.wsgi.application'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
)

# To get access to some global variables used in the templates
TEMPLATE_CONTEXT_PROCESSORS = DEFAULT_SETTINGS.TEMPLATE_CONTEXT_PROCESSORS + (
    'question.context_processors.global_template_variables',
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    'django.contrib.admindocs',
    'django.contrib.humanize',

    # 3rd party apps
    #'south',
    #'dajax',

    # Our apps
    'person',
    'tagging',
    'question',
    'course',
    'instructor',
    'utils',
    'grades',
    'stats'
)

# Authentication related:
AUTH_PROFILE_MODULE = 'person.UserProfile'

# Exec the local settings (settings that should not be included in version
# control!
QUEST = {}
this_dir = __file__[0:__file__.find('settings.py')]
try:
    #pass
    execfile(this_dir + os.sep + 'local_settings.py')
except IOError:
    # See https://docs.djangoproject.com/en/1.5/ref/settings for EMAIL settings
    EMAIL_HOST = ''
    EMAIL_HOST_USER = ''
    EMAIL_HOST_PASSWORD = ''
    # Visitors will receive email from this address e.g. "admin@example.org"
    SERVER_EMAIL = ''
    DEFAULT_FROM_EMAIL = SERVER_EMAIL


# What is the location for media generated by the software:
# The general location should be mounted under your ``MEDIA_ROOT``. This is
# where we will write images to and where students will upload media to
QUEST['MEDIA_LOCATION'] = MEDIA_ROOT + '%s' + os.sep

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': ('%(asctime)s,%(levelname)s,%(filename)s,%(lineno)d,'
                       '[%(funcName)s(...)] : %(message)s')
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
            'require_debug_false': {
                '()': 'django.utils.log.RequireDebugFalse'
            }
        },
    'handlers': {
        'null': {
            'level':'DEBUG',
            'class':'django.utils.log.NullHandler',
        },

        'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter': 'simple'
        },

        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler'
        },

        'file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'verbose',
            # Inputs to the ``logging.handlers.RotatingFileHandler`` class
            'filename': QUEST['logfile_location'],
        },
    },

    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            #'filters': ['require_debug_false'],
            'level': 'ERROR',
            'propagate': True,
        },
        'quest': {
            'handlers': ['file', 'mail_admins'],
            #'filters': ['require_debug_false'],
            'level': 'DEBUG',
            'propagate': True,
        },
    }
}
