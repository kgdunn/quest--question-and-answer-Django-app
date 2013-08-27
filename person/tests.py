from django.test import TestCase
from django.test.client import Client
from django.core.urlresolvers import reverse
from person.models import Token, UserProfile, Timing
from django.conf import settings
from instructor.views import (create_question_template, render)
from course.models import Course
from question.models import (QTemplate, QActual, QSet)
import datetime

try:
    import wingdbstub
except ImportError:
    pass

#def test_login_during_second_time(self):
    #pass

#def test_login_during_second_time_different_browser(self):
    #pass

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
                                               reverse('quest-course-selection'))

    def test_student_process(self):
        """ Create a QSet that is currently valid; check that the user can
        sign in an answer questions.
        """
        # Let's add a template, a QSet and render an actual question
        some_text = ('[[type]]\nMCQ\n[[question]]\nIf a=1, b=2. What is a*b?\n'
                     '--\n& 12\n&1\n^THE_SOLUTION\n& 4\n')

        user = UserProfile.objects.filter(role='Grader')[0]
        qtemplate = create_question_template(some_text, user=user)
        qt = QTemplate.objects.get(id=qtemplate.id)
        course = Course.objects.all()[0]
        qset = QSet.objects.create(name="TEMPORARY-TEST", course=course)

        # Render a question for the student
        student = UserProfile.objects.filter(role='Student')[0]
        html_q, html_a, var_dict, grading_answer = render(qt)
        qa = QActual.objects.create(qtemplate=qt,
                                    qset=qset,
                                    user=student,
                                    as_displayed=html_q,
                                    html_solution=html_a,
                                    var_dict=var_dict,
                                    grading_answer=grading_answer)


        now = datetime.datetime.now()
        delta = datetime.timedelta(seconds=600)
        qset.ans_time_start = now - delta
        qset.ans_time_final = now + delta
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
                                            reverse('quest-course-selection'))

        resp = self.client.get(reverse('quest-course-selection'))
        self.assertEqual(resp.templates[0].name, 'question/course-selection.html')
        self.assertEqual(resp.templates[1].name, 'question/questions.html')
        start = resp.content.find('TEMPORARY-TEST')
        url = resp.content[start-200:start].split(r'<a href="')
        explode = url[-1].split('/')
        to_get = '/' + '/'.join([item for item in explode if item.strip('">')])



        resp = self.client.get(reverse('quest-question-set',
                                       args=(qset.course.slug, )))
        self.assertEqual(resp.templates[0].name, 'question/question-sets.html')
        self.assertEqual(resp.templates[1].name, 'question/questions.html')
        start = resp.content.find('TEMPORARY-TEST')
        url = resp.content[start-200:start].split(r'<a href="')
        explode = url[-1].split('/')
        to_get = '/' + '/'.join([item for item in explode if item.strip('">')])

        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 0)

        # Test is in the future still
        #----------------------------------
        qset.ans_time_start = now + delta
        qset.ans_time_final = now + 2*delta
        qset.save()
        resp = self.client.get(to_get, follow=True)
        self.assertEqual(resp.templates[0].name, 'question/not-started-yet.html')
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 0)

        # Make it that test can be started. Check that the time remaining is
        # accurate. Check that the solutions are NOT displayed.
        #------------------------------------
        qset.ans_time_start = now - delta
        qset.ans_time_final = now + delta
        qset.save()

        resp = self.client.get(to_get, follow=True)

        # First there is an honesty check
        self.assertEqual(resp.templates[0].name, 'question/honesty-check.html')
        start = resp.content.find('Start the Quest')
        url = resp.content[start-200:start].split(r'<a href="')
        explode = url[-1].split('/')
        to_get = '/' + '/'.join([item for item in explode if item.strip('">')])

        # Then we can start the test
        resp = self.client.get(to_get, follow=True)
        self.assertEquals(self.client.session['expires'], qset.ans_time_final)
        self.assertTrue(resp.context['minutes_left'] in (9, 10))
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'question/question-list.html')
        self.assertEqual(timer[0].final_time, qset.ans_time_final)

        # And verify the solutions are NOT visible
        resp = self.client.get(reverse('quest-ask-specific-question', args=(
                                                        qset.course.slug,
                                                        qset.slug,
                                                        1)))
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
        self.assertEqual(resp.context['html_solution'], '')
        self.assertTrue(resp.context['minutes_left'] in (9, 10))

        # Now create a QSet that has a specified duration, different from
        # the default finishing time. Let the finishing time be 5 minutes away.
        # Delete out the old timers; start with a new client and a new session.
        # We have to sign in again with the same token.
        #---------------------------------------------------------------------
        qset.max_duration = datetime.time(minute=5)
        qset.save()

        timer = Timing.objects.filter(user=user[0], qset=qset)
        timer[0].delete()
        c = Client(HTTP_USER_AGENT='ABC')
        resp = c.get(reverse('quest-token-sign-in',
                              args=(su_token.token_address,)), follow=True)
        before = datetime.datetime.now()
        resp = c.get(to_get, follow=True)  # will return the honesty check
        resp = c.get(to_get, follow=True)  # will continue on after the honesty
        self.assertTrue(resp.context['minutes_left'] in (4, 5))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'question/question-list.html')
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)

        mins_left_session = (c.session['expires'] - before).seconds//60
        self.assertTrue(mins_left_session in (4,5))

        mins_left_timer = (timer[0].final_time - before).seconds//60
        self.assertTrue(mins_left_timer in (4,5))

        # And verify the solutions are NOT visible
        resp = c.get(reverse('quest-ask-specific-question', args=(
                                                        qset.course.slug,
                                                        qset.slug,
                                                        1)))
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
        self.assertEqual(resp.context['html_solution'], '')
        self.assertTrue(resp.context['minutes_left'] in (4, 5))



        # Now create a QSet that has a specified duration of 5 minutes.
        # But the user signs in 3 minutes before the end of the test.
        # Delete out the old timers; start with a new client and a new session.
        # We have to sign in again with the same token.
        #----------------------------------------------------------------------
        qset.max_duration = datetime.time(minute=5)
        qset.ans_time_final = now + datetime.timedelta(seconds=180)
        qset.save()

        timer[0].delete()
        c = Client(HTTP_USER_AGENT='DEF')
        resp = c.get(reverse('quest-token-sign-in',
                              args=(su_token.token_address,)), follow=True)
        before = datetime.datetime.now()
        resp = c.get(to_get, follow=True)
        resp = c.get(to_get, follow=True)  # by-pass the honesty check again
        self.assertTrue(resp.context['minutes_left'] in (2, 3))
        self.assertEqual(resp.status_code, 200)
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)

        mins_left_session = (c.session['expires'] - before).seconds//60
        self.assertTrue(mins_left_session in (2, 3))

        mins_left_timer = (timer[0].final_time - before).seconds//60
        self.assertTrue(mins_left_timer in (2, 3))

        resp = c.get(reverse('quest-ask-specific-question', args=(
                                                        qset.course.slug,
                                                        qset.slug,
                                                        1)))
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
        self.assertEqual(resp.context['html_solution'], '')
        self.assertTrue(resp.context['minutes_left'] in (2, 3))



        # Now create a QSet that has expired already.
        # The user signs in and can see the solutions.
        #--------------------------------------------------------------------
        qset.ans_time_final = now - datetime.timedelta(seconds=5)
        qset.save()

        timer = Timing.objects.filter(user=user[0], qset=qset)
        timer[0].delete()
        c = Client(HTTP_USER_AGENT='GHI')
        resp = c.get(reverse('quest-token-sign-in',
                              args=(su_token.token_address,)), follow=True)
        before = datetime.datetime.now()
        resp = c.get(to_get, follow=True)
        self.assertEquals(resp.context['minutes_left'], 0)
        self.assertEquals(resp.context['seconds_left'], 0)
        self.assertEqual(resp.status_code, 200)
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 0)  # no timer gets created

        mins_left_session = (c.session['expires'] - before).seconds//60
        self.assertTrue(mins_left_session in (59, 60))

        # And verify the solutions are visible
        resp = c.get(reverse('quest-ask-specific-question', args=(
                                                        qset.course.slug,
                                                        qset.slug,
                                                        1)))
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
        self.assertTrue(resp.context['html_solution'].find('THE_SOLUTION')>0)
        self.assertTrue(resp.context['minutes_left'] == 0)


        # Now create a QSet that has a specified duration of 5, yes 5, seconds.
        # But the user signs in and tries to answer a question after their time
        # has expired.
        # Delete out the old timers; start with a new client and a new session.
        # We have to sign in again with the same token. Change the expiry
        # date of their session during this test and compare the results.
        #----------------------------------------------------------------------
        qset.max_duration = datetime.time(second=5)
        qset.ans_time_final = now + datetime.timedelta(seconds=500)
        qset.save()

        timer = Timing.objects.filter(user=user[0], qset=qset)
        if timer:
            timer[0].delete()
        c = Client(HTTP_USER_AGENT='UVW')
        resp = c.get(reverse('quest-token-sign-in',
                              args=(su_token.token_address,)), follow=True)
        before = datetime.datetime.now()
        resp = c.get(to_get, follow=True)
        resp = c.get(to_get, follow=True)  # by-pass the honesty check

        self.assertEqual(resp.status_code, 200)
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)

        mins_left_session = (c.session['expires'] - before).seconds//60
        self.assertTrue(mins_left_session == 0)

        mins_left_timer = (timer[0].final_time - before).seconds//60
        self.assertTrue(mins_left_timer == 0)

        # Now sleep 5 seconds; waiting for the QSet to expire.
        import time
        time.sleep(5)

        # Now attempt to answer the questions. Should not be able to.
        resp = c.get(reverse('quest-ask-specific-question', args=(
                                                        qset.course.slug,
                                                        qset.slug,
                                                        1)))
        self.assertEqual(resp.templates[0].name, 'question/time-expired.html')
        self.assertTrue(resp.context['solution_time'] == qset.ans_time_final)
