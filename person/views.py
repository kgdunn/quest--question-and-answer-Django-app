import models
import logging
import datetime

from django.conf import settings
from django.core.urlresolvers import reverse
from django.core.context_processors import csrf
from django.contrib.auth import login, authenticate
from django.shortcuts import render_to_response, redirect, RequestContext

# Our apps:
from models import Token
from utils import generate_random_token, send_email

# http://quest.mcmaster.ca/tokens/
# The Django ``reverse`` function is one of the hardest functions to get
# working. Here's my attempt (not working):
#    token_addr = reverse('quest-token-sign-in', 'quest', args=['random_token'])
token_addr = 'tokens'
token_prefix = 'http://%s/%s/' % (settings.QUEST['FULL_DOMAIN_NO_HTTP'],
                                  token_addr)


logger = logging.getLogger('quest')

def create_new_account(user=None, **kwargs):
    """
    Complete creating the new user account: i.e. a new ``User`` object.

    This is a signal that is caught when we create a new user.
    """
    if 'instance' in kwargs and kwargs.get('created', False):
        new_user = kwargs.get('instance', user)

        # Create a UserProfile object in the DB
        new_user_profile = models.UserProfile.objects.create(user=new_user)
        new_user_profile.save()


def create_sign_in_email(user, qset=None):
    """
    Creates the token and generates the email body and subject for a user.
    """
    token_address = generate_random_token()
    Token.objects.get_or_create(token_address=token_address,
                                user=user,
                                has_been_used=False)
    token_address = token_prefix + token_address
    message = """\
    This message has been sent so you may access the Quest website.

    Sign in at: %s

    You may re-use this link within the testing duration, or request a new link
    from http://quest.mcmaster.ca\n\n""" % token_address

    if qset:
        subject = 'Quest website, %s' % qset.name
        message += """
    * Test duration = %s hours and %s minute(s).
    * Testing window closes at: %s; after which solutions are available.""" % \
          (qset.max_duration.strftime('%H'),
           qset.max_duration.strftime('%M'),
           qset.ans_time_final.strftime('%H:%M on %d %h %Y'))
    else:
        subject = 'Quest website access'

    message += """

    Please note: negative grading will be used for multiple-selection answers.
    In other words, do not check an answer unless you are certain it is correct.
    Negative grading is -0.5 points per incorrect selection.

    The http://quest.mcmaster.ca web server.
    """

    return subject, message, user.email


def sign_in(request):                             # URL: 'quest-main-page'
    """
    Verifies the user. If they are registered, then they are emailed a
    token to sign in.
    """
    if request.method == 'POST':
        email = request.POST.get('user_mail_address', '')
        logger.info('POST::person::sign-in: ' + email)

        try:
            user = models.User.objects.get(email=email)
        except models.User.DoesNotExist:
            # If email not in list, tell them they are not registered
            page_content = {}
            ctxdict = {}
            ctxdict.update(csrf(request))
            return render_to_response('person/not-registered.html', ctxdict,
                                    context_instance=RequestContext(request))

        else:
            subject, message, to_address = create_sign_in_email(user)
            out = send_email([to_address, ], subject, message)
            if out:
                logger.debug('Successfully sent email for sign in')
            else:
                logger.error('Unable to send sign-in email to: %s' %
                            to_address[0])

            ctxdict = {}
            ctxdict.update(csrf(request))
            return render_to_response('person/sent-email.html', ctxdict,
                                    context_instance=RequestContext(request))

    # Non-POST access of the sign-in page: display the login page to the user
    else:
        ctxdict = {'email_placeholder': 'xxxxxxxx%s'  %
                                         settings.QUEST['email_placeholder']}
        ctxdict.update(csrf(request))
        return render_to_response('person/sign-in-form.html', ctxdict,
                                  context_instance=RequestContext(request))


def token_sign_in(request, token):  # URL: 'quest-token-sign-in'
    """ Signs the user in for a limited period.
    """
    logger.debug('About to process received token: ' + str(token))
    token_item = Token.objects.filter(token_address=token)

    if len(token_item) == 0 or token_item[0].has_been_used:
        logger.info('Invalid/expired token received: ' + token)
        page_content = {}
        ctxdict = {}
        ctxdict.update(csrf(request))
        return render_to_response('person/invalid-expired-token.html',
                                  ctxdict,
                                  context_instance=RequestContext(request))

    # Valid token found. Continue on.
    user = token_item[0].user

    # Use Django's auth framework to mark the user as signed-in
    # authenticate() <--- use this in the future to authenticate against
    #                     other systems. We are using tokens for now.
    user = authenticate(remote_user=user.username)
    login(request, user)

    # Now proceed to show available question sets to the user
    response = redirect('quest-question-set')
    request.session['token'] = token
    return response
