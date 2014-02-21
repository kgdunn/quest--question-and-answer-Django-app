from django.conf.urls import patterns, include, url
from django.conf import settings
import views
from grades.views import grade_peer_eval, email_user_feedback

urlpatterns = patterns('',

    # NOTE: all these URLs are preceded by "_admin/"


    #url(r'load-class-list/$', views.load_class_list, name='admin-load-class-list'),
    url(r'load-class-list/$', views.load_class_list, name='admin-load-class-list'),

    url(r'generate-questions/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$',
        views.generate_questions, name='admin-generate-questions'),

    url(r'load-from-template/$', #(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/',
        views.load_from_template, name='admin-load-from-template'),

    url(r'report-responses/',
        views.report_responses, name='admin-report-responses'),

    url(r'report-responses-short-answer/',
            views.report_responses_short_answer,
            name='admin-report-responses-short-answer'),

    #url(r'fix-questions/', views.fix_questions),

    url('preview-question/', views.preview_question,
        name='admin-preview-question'),

    url('grade-peer-eval/', grade_peer_eval, name='admin-grade-peer-eval'),

    url('email-user-feedback', email_user_feedback, name="admin-email-user-feedback")

)