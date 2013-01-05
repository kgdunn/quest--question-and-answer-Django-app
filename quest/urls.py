from django.conf.urls import patterns, include, url
import person
from question.views import(ask_question_set, ask_show_questions,
                           ask_specific_question)
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
    urlpatterns = patterns()

urlpatterns += patterns('',
    # Examples:
    # url(r'^$', 'quest.views.home', name='home'),
    # url(r'^quest/', include('quest.foo.urls')),
    url(r'^$', person.views.sign_in, name='quest-main-page'),
    url(r'^tokens/(.*)/$', person.views.deactivate_token_sign_in),

    url(r'^question-sets/$', ask_question_set, name='quest-question-set'),

    # ://(course-code)/(question-set-slug)/(question-id)/
    url(r'^(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/(?P<question_id>.+)/$', ask_specific_question, name='quest-ask-specific-question'),

    # ://(course-code)/(question-set-slug)/
    url(r'^(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/', ask_show_questions, name='quest-ask-show-questions'),



    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)