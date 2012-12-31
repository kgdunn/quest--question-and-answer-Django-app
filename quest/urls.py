from django.conf.urls import patterns, include, url
import person
from question.views import ask_question_set, ask_show_questions

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'quest.views.home', name='home'),
    # url(r'^quest/', include('quest.foo.urls')),
    url(r'^$', person.views.sign_in, name='quest-main-page'),

    url(r'^question-sets/$', ask_question_set, name='quest-question-set'),

    # ://(course-code)/(question-set-slug)/
    url(r'^(?P<course_code>.*)/(?P<question_set>.*)/$', ask_show_questions,
        name='quest-ask-questions'),

    (r'^tokens/(.*)/$', person.views.deactivate_token_sign_in),


    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)
