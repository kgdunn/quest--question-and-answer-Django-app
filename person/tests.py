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

        # First there is an honesty check
        self.assertEqual(resp.templates[0].name, 'question/honesty-check.html')

        to_get = to_get.replace('/set/', '/honesty-check/')
        resp = self.client.get(to_get, follow=True)
        self.assertEqual(resp.templates[0].name, 'question/question-list.html')
        to_get = to_get.replace('/honesty-check/', '/question/') + '/1/'
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
        self.assertTrue(resp.context['minutes_left'] in (9, 10))
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
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
        resp = c.get(to_get, follow=True)
        self.assertTrue(resp.context['minutes_left'] in (4, 5))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.templates[0].name, 'question/single-question.html')
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)

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

        self.assertTrue(resp.context['minutes_left'] in (2, 3))
        self.assertEqual(resp.status_code, 200)
        timer = Timing.objects.filter(user=user[0], qset=qset)
        self.assertEqual(len(timer), 1)

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


        # Can view the solutions to a prior quest, while the current quest
        # is in progress
        # Let's add a template, a QSet and render an actual question
        # -----------------------------------------------------------
        some_text = ('[[type]]\nMCQ\n[[question]]\nLet a=2, b=4. What is a+b?\n'
                     '--\n& 8\n&2\n^6\n& 1\n')

        user = UserProfile.objects.filter(role='Grader')[0]
        qtemplate = create_question_template(some_text, user=user)
        qt = QTemplate.objects.get(id=qtemplate.id)
        course = Course.objects.all()[0]
        qset_curr = QSet.objects.create(name="CURRENT-TEST", course=course)

        # Render a question for the student
        student = UserProfile.objects.filter(role='Student')[0]
        html_q, html_a, var_dict, grading_answer = render(qt)
        qa = QActual.objects.create(qtemplate=qt,
                                    qset=qset_curr,
                                    user=student,
                                    as_displayed=html_q,
                                    html_solution=html_a,
                                    var_dict=var_dict,
                                    grading_answer=grading_answer)


        now = datetime.datetime.now()
        delta = datetime.timedelta(seconds=600)
        qset_curr.ans_time_start = now - delta
        qset_curr.ans_time_final = now + delta
        qset_curr.save()

        # Retrieve the prior test, and make sure it has expired (i.e. its
        # solutions are available)
        qset_prior = QSet.objects.filter(name="TEMPORARY-TEST", course=course)[0]
        qset_prior.ans_time_final = now - delta
        qset_prior.ans_time_start = now - 2*delta
        qset_prior.save()
        # Verify the solutions are visible for the older QSet
        url_old = reverse('quest-ask-specific-question', args=(
                                                        qset_prior.course.slug,
                                                        qset_prior.slug,
                                                        1))
        url_curr = reverse('quest-ask-specific-question', args=(
                                                        qset_curr.course.slug,
                                                        qset_curr.slug,
                                                        1))

        resp_old = c.get(url_old)
        resp_curr = c.get(url_curr)

        self.assertEqual(resp_old.templates[0].name, 'question/single-question.html')
        self.assertEqual(resp_curr.templates[0].name,'question/single-question.html')

        self.assertTrue(resp_old.context['html_solution'].find('THE_SOLUTION')>0)
        self.assertTrue(resp_old.context['html_solution'].find('The solution is')>0)
        self.assertTrue(resp_curr.context['html_solution'].find('THE_SOLUTION')==-1)
        self.assertTrue(resp_curr.context['html_solution'].find('The solution is')==-1)
        self.assertTrue(resp_old.context['minutes_left'] == 0)
        self.assertTrue(resp_curr.context['minutes_left'] in (9, 10))


    # Tests to write still
    # --------------------
    # Submit the quests
    # Check that unanswered questions are highlighted
    # Check that honesty reuqest is displayed
    # Check that successfully submitted response screen shows the token
    # Check that an email was sent to the student on successful submission
    # Check that the student cannot sign in again with that token
    # Check that the student cannot sign in again if time has expired
    # Check that student CAN sign in again, with a new token, if time remains

