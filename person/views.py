import models
import logging

from django.core.context_processors import csrf
from django.shortcuts import render_to_response
from django.http import HttpResponseRedirect

from models import Token

# Our apps:
from utils import generate_random_token, send_email

# Move to "settings.py" later on
email_suffix = '@mcmaster.ca'  # and make it part of the sign-in-form.html template also
email_from = 'Quest Website <kevin.dunn@mcmaster.ca>'
token_prefix = 'http://quest.mcmaster.ca/tokens/'

logger = logging.getLogger('quest')
logger.debug('Initializing person::views.py')

#from django.contrib.auth import authenticate, login

def user_logged_in(user, **kwargs):
    """
    Triggered when the user signs in.
    """
    logger.debug('User logged in: %s' % user.username)

def create_new_account(user=None, **kwargs):
    """
    Complete creating the new user account: i.e. a new ``User`` object.

    This is a signal that is caught when the ``registration`` module creates a
    new user.
    """
    if 'instance' in kwargs and kwargs.get('created', False):
        new_user = kwargs.get('instance', user)

        # Create a UserProfile object in the DB
        new_user_profile = models.UserProfile.objects.create(user=new_user)
        new_user_profile.save()

def sign_in(request, next_page=''):
    """
    Verifies the user. If they are registered, then they are emailed a
    token to sign in.
    """
    logger.debug('person::sign-in')
    if request.method == 'POST':
        form_email_prefix = request.POST.get('email_prefix', '')
        email = form_email_prefix + email_suffix
        logger.info('POST::person::sign-in: ' + email)

        try:
            the_student = models.User.objects.get(email=email)
        except models.User.DoesNotExist:
            # If email not in list, tell them they are not registered
            page_content = {}
            return render_to_response('person/not-registered.html',
                                      page_content)

        else:
            token_address = generate_random_token()
            Token.objects.get_or_create(token_address=token_address,
                                        user=the_student,
                                        has_been_used=False)
            token_address = token_prefix + token_address
            email_token_to_student([the_student.email, ], token_address)
            return render_to_response('person/sent-email')

    # Non-POST access of the sign-in page: display the login page to the user
    else:
        logger.debug('Non-POST sign-in page request')
        page_content = {}
        page_content.update(csrf(request))
        return render_to_response('person/sign-in-form.html', page_content)

def email_token_to_student(to_address, token_address):
    """ Sends an email to the student with the web address to log in."""

    message = '''\
This message has been sent, at your request, to access the Quest website.

The web address will only work ONCE: ''' + token_address + '''\

You can re-request access as many times as you like. There is no need to log
in or log out afterwards - just close the web page.

The http://quest.mcmaster.ca web server.
'''
    subject = 'Access the Quest website'
    out = send_email(to_address, subject, message, from_address=email_from)

