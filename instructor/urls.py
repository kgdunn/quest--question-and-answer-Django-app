from django.conf.urls import patterns, include, url
from django.conf import settings
import views

urlpatterns = patterns('',

    # NOTE: all these URLs are preceded by "_admin/"


    url(r'load-class-list/$', views.load_class_list, name='admin-load-class-list'),


    url(r'generate-questions/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', views.generate_questions, name='admin-generate-questions'),

    ## The final check and the actual submission of answers go through this URL
    #url(r'^submit-final-check/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', submit_answers, name='quest-submit-final-check'),

    ## ://store/(course-code)/(question-set-slug)/(question-id)/
    #url(r'^store/(?P<course_code_slug>.*)/(?P<question_set_slug>.*)/(?P<question_id>.*)/$', store_answer, name='quest-store-answer'),

    ## ://(course-code)/(question-set-slug)/(question-id)/
    #url(r'^(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/(?P<question_id>.+)/$', ask_specific_question, name='quest-ask-specific-question'),

    ## ://(course-code)/(question-set-slug)/
    #url(r'^(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/', ask_show_questions, name='quest-ask-show-questions'),

)