import models
import logging
import datetime

from django.conf import settings
from django.core.urlresolvers import reverse, Http404
from django.http import HttpResponseRedirect
from django.core.context_processors import csrf
from django.contrib.auth import login, authenticate
from django.views.generic.base import View
from django.shortcuts import (HttpResponse, render_to_response, redirect,
                              RequestContext)

# Our apps:
from models import Token
from utils import generate_random_token, send_email
from stats.models import Profile, TimerStart
from stats.views import get_profile

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
    # Adjust the length of the authentication token here
    token_address = generate_random_token(token_length=10)
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
    * Testing window closes at: %s.""" % \
          (qset.duration().hour,
           qset.duration().minute,
           qset.ans_time_final.strftime('%H:%M on %d %h %Y'))
    else:
        subject = 'Quest website access'

    #message += """

    #Please note: negative grading will be used for multiple-selection answers.
    #In other words, do not check an answer unless you are certain it is correct.
    #Negative grading is -0.5 points per incorrect selection.
    #"""

    message += """
    The http://quest.mcmaster.ca web server.
    """

    return subject, message, user.email


def sign_in(request):                        # URL: 'quest-main-page'
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


def mcmaster_macid_sign_in_success(request, *args, **kwargs):
    """
    For McMaster MacID sign in
    """
    logger.info('args = %s' % str(args))
    logger.info('kwargs = %s' % str(kwargs))
    logger.info('GET = %s' % str(request.GET))


    # Download from http://twhiteman.netfirms.com/des.html
    from pyDes import PAD_PKCS5, CBC, triple_des
    from zlib import decompress, compress

    #  UTS instructions: Decode the token using Hex decoding.
    #                    Then you will decrypt it using 3DES CBC with PKCS5 Padding.
    #                    The final step would be to unzip using gzip.


    # -----------------
    # Try an example
    # -----------------

    # Try to simulate encryption, compression, and encoding
    KEY = 'a1b2c3D4E5s6j329dj432123'
    plain_message = 'mcauth1.02:3EEA96245BA36E1C6F469F5B5914BDB6:1343408970:192.168.1.1:sayede:yes'

    k_encrypt = triple_des(key, mode=CBC, padmode=PAD_PKCS5) # initialize key
    encrypted_message = k_encrypt.encrypt(plain_message)

    zipped_encrypted_message = compress(encrypted_message)
    token = zipped_encrypted_message.encode('hex')


    # # Then decode, decompress, deencrypt it
    def decode_token(token):
        token_zip = token.decode('hex')
        token_encrypted = decompress(token_zip)
        k_decrypt = triple_des(KEY, mode=CBC, padmode=PAD_PKCS5)
        decrypted_message = k_decrypt.decrypt(token_encrypted)
        return decrypted_message

    assert(zipped_encrypted_message == token_zip)
    assert(encrypted_message == token_encrypted)
    assert(decrypted_message == plain_message)


    # -----

    token1='e884fd0eca16d7f49ef8d83ce2d13adb2a95b0e788f07b318bb91667c4398862ccf09372e8239e66126fc80699bb630c8be06d0bb96e200032d4533f39228afd833881095bc7d6a9fe4e6c6fcc06b34e83d09b56c86b94a6e2ac64170072bcc0a82246a27dd270da'
    token2='e884fd0eca16d7f423034c0d47574858eea93b21154af966da5cf6be06712a60e9865f083d7643bc2c8716087eb0f7f480068378be5debdd46a43be8dcccda9987ca6b070fe19d94b0a0420e8d13a2f6060c148a03173656fbfba814eb1262f4e41bd111beb1cc54'
    token_hex_zip = token.decode('hex')
    decompressed = decompress(token_hex_zip)
    KEY = 'tr3bRujupa9e!ec6uSp4wr37'
    k = triple_des(key, mode=CBC, padmode=PAD_PKCS5)
    decrypted = k.decrypt(decompressed)


    return HttpResponse('This is the success URL')


class TokenSignIn(View):                    # URL: 'quest-token-sign-in'
    """ Signs the user in for a limited period.  """
    def get(self, request, token):
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

        TimerStart.objects.create(event='login',
                                user=request.user.profile,
                                profile=get_profile(request),
                                item_pk=user.id,
                                item_type='User',
                                referrer=request.META.get('HTTP_REFERER', ''))

        # Now proceed to show available question sets to the user
        # response = redirect('quest-course-selection')
        request.session['token'] = token
        request.session.save()

        # AJAX request to store user's profile in a session key appears in the
        # HTML for the redirect above.
        return HttpResponseRedirect(reverse('quest-course-selection'))
