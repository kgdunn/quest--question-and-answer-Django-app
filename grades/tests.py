from django.test import TestCase
#from django.test.client import Client
#from django.core.urlresolvers import reverse
#from person.models import Token, UserProfile, Timing
#from django.conf import settings
#from instructor.views import (create_question_template, render)
#from course.models import Course
#from question.models import (QTemplate, QActual, QSet)
#import datetime

try:
    import wingdbstub
except ImportError:
    pass

#class Login_TestCases(TestCase):
    #def test_login_before_start(self):
        #c = Client(HTTP_USER_AGENT='ABC')  # enforce_csrf_checks=True,
        #resp = c.get('/')#, {'username': 'john', 'password': 'smith'})

        #self.assertEqual(resp.templates[1].name, 'base.html')
        #self.assertEqual(resp.templates[0].name, 'person/sign-in-form.html')

        #self.assertEquals(resp.status_code, 200)

        ## Now sign-in with an email address

        #settings.TESTING = True  # to prevent emails being sent
        #n_tokens = len(Token.objects.all())
        #user = UserProfile.objects.filter(role='Student')
        #if user:
            #email = user[0].user.email
            #resp = c.post('/', {'user_mail_address': email})
            #self.assertEquals(resp.status_code, 200)
            #self.assertEqual(n_tokens+1, len(Token.objects.all()))
            #self.assertEqual(resp.templates[0].name, 'person/sent-email.html')
        #else:
            #pass


# Tests to add
# --------------

# \u2212 = "-"