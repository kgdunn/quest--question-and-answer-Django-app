from django.test import TestCase
from django.test.client import Client
from django.core.urlresolvers import reverse
from person.models import Token, UserProfile
from django.conf import settings
from instructor.views import (create_question_template, render)
from course.models import Course
from question.models import (QTemplate, QActual, QSet)
import datetime

import wingdbstub

class Login_TestCases(TestCase):
    def test_login_before_start(self):
        c = Client(HTTP_USER_AGENT='ABC')  # enforce_csrf_checks=True,
        resp = c.get('/')#, {'username': 'john', 'password': 'smith'})

        self.assertEqual(resp.templates[1].name, 'base.html')
        self.assertEqual(resp.templates[0].name, 'person/sign-in-form.html')

        self.assertEquals(resp.status_code, 200)

        # Now sign-in with an email address

        settings.TESTING = True  # to prevent emails being sent
        n_tokens = len(Token.objects.all())
        user = UserProfile.objects.filter(role='Student')
        if user:
            email = user[0].user.email
            resp = c.post('/', {'user_mail_address': email})
            self.assertEquals(resp.status_code, 200)
            self.assertEqual(n_tokens+1, len(Token.objects.all()))
            self.assertEqual(resp.templates[0].name, 'person/sent-email.html')
        else:
            pass

    def test_invalid_user(self):
        """User does not exist"""
        c = Client(HTTP_USER_AGENT='ABC')
        resp = c.post('/', {'user_mail_address': '____@example.FALSE'})
        self.assertEquals(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'person/not-registered.html')

    def test_login_after_final(self):
        pass

    def test_login_superuser(self):
        """ Superuser check
        """
        c = Client(HTTP_USER_AGENT='ABC')  # enforce_csrf_checks=True,
        settings.TESTING = True  # to prevent emails being sent
        user = UserProfile.objects.filter(role='Superuser')
        if user:
            email = user[0].user.email
            resp = c.post('/', {'user_mail_address': email})
            self.assertEquals(resp.status_code, 200)
            self.assertEqual(resp.templates[0].name, 'person/sent-email.html')
        else:
            return

        su_token = Token.objects.latest('id')

        # Sign in with this token
        resp = self.client.get(reverse('quest-token-sign-in',
                                       args=(su_token.token_address,)))
        self.assertEqual(resp.templates, [])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'http://testserver%s' %
                                               reverse('quest-question-set'))

    def test_login_during_time(self):
        """ Create a QSet that is currently valid; check that the user can
        sign in an answer questions.
        """
        # Let's add a template, a QSet and render an actual question
        some_text = ('[[type]]\nMCQ\n[[question]]\nIf a=1, b=2. What is a*b?\n'
                     '--\n& 12\n&1\n^2\n& 4\n')
        qtemplate = create_question_template(some_text)
        qt = QTemplate.objects.get(id=qtemplate.id)

        course = Course.objects.all()[0]
        qset = QSet.objects.create(name="TEMPORARY-TEST", course=course)

        student = UserProfile.objects.filter(role='Student')[0]
        qa = render(qt, qset, student.user)

        now = datetime.datetime.now()
        previous = datetime.timedelta(seconds=600)
        qset.ans_time_start = now - previous
        qset.ans_time_final = now + previous
        qset.save()

        # Now sign in as a student
        c = Client(HTTP_USER_AGENT='ABC')  # enforce_csrf_checks=True,
        settings.TESTING = True  # to prevent emails being sent
        user = UserProfile.objects.filter(role='Student')
        email = user[0].user.email
        resp = c.post('/', {'user_mail_address': email})
        self.assertEquals(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'person/sent-email.html')

        su_token = Token.objects.latest('id')

        # Sign in with this token
        resp = self.client.get(reverse('quest-token-sign-in',
                                       args=(su_token.token_address,)))
        self.assertEqual(resp.templates, [])
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], 'http://testserver%s' %
                                               reverse('quest-question-set'))

        resp = self.client.get(reverse('quest-question-set'))
        self.assertEqual(resp.templates[0].name, 'question/question-sets.html')
        self.assertEqual(resp.templates[1].name, 'question/questions.html')
        start = resp.content.find('TEMPORARY-TEST')
        url = resp.content[start-200:start].split(r'<a href="')
        explode = url[-1].split('/')
        to_get = '/' + '/'.join([item for item in explode if item.strip('">')])
        resp = self.client.get(to_get, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'question/question-list.html')







    def test_login_during_second_time(self):
        pass

    def test_login_during_second_time_different_browser(self):
        pass

