from django.test import TestCase
from django.test.client import Client
import wingdbstub

class LoginTest(TestCase):
    def test_login_before_start(self):
        c = Client(enforce_csrf_checks=True,
                   HTTP_USER_AGENT='ABC')
        response = c.get('/')#, {'username': 'john', 'password': 'smith'})
        self.assertEquals(response.templates[0].name,
                          'person/sign-in-form.html')
        self.assertEquals(response.status_code, 200)
        response = c.post('/', {'user_mail_address': 'dunnkg@mcmaster.ca'})


    def test_login_after_final(self):
        pass

    def test_login_during_time(self):
        pass

    def test_login_during_second_time(self):
        pass

    def test_login_during_second_time_different_browser(self):
        pass

