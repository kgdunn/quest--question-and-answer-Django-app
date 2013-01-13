from django.conf.urls import patterns, include, url
import person
import instructor
from question.views import(ask_question_set, ask_show_questions,
                           ask_specific_question, store_answer,
                           submit_answers, successful_submission)
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

if settings.DEBUG:
    # Small problem: cannot show 404 templates /media/....css file, because
    # 404 gets overridden by Django when in debug mode
    urlpatterns = patterns(
        '',
        (r'^media/(?P<path>.*)$',
         'django.views.static.serve', {'document_root': settings.MEDIA_ROOT}),
    )
else:
    urlpatterns = patterns('')

urlpatterns += patterns('',

    (r'^favicon\.ico$', 'django.views.generic.simple.redirect_to', {'url': '/media/favicon.ico'}),

    # Instructor specific URLs
    url(r'^_admin/', include('instructor.urls')),

    url(r'^$', person.views.sign_in, name='quest-main-page'),

    url(r'^tokens/(.*)/$', person.views.deactivate_token_sign_in, name='quest-deactivate'),

    url(r'^question-sets/$', ask_question_set, name='quest-question-set'),

    url(r'^successfully-submitted/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', successful_submission, name='quest-successful-submission'),

    # The final check and the actual submission of answers go through this URL
    url(r'^submit-final-check/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', submit_answers, name='quest-submit-final-check'),

    # ://store/(course-code)/(question-set-slug)/(question-id)/
    url(r'^store/(?P<course_code_slug>.*)/(?P<question_set_slug>.*)/(?P<question_id>.*)/$', store_answer, name='quest-store-answer'),

    # ://question/(course-code)/(question-set-slug)/(question-id)/
    url(r'^question/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/(?P<question_id>.+)/$', ask_specific_question, name='quest-ask-specific-question'),

    # ://(course-code)/(question-set-slug)/
    url(r'^set/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/', ask_show_questions, name='quest-ask-show-questions'),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)