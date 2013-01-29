from django.conf.urls import patterns, include, url
from django.conf import settings
import views

urlpatterns = patterns('',

    # NOTE: all these URLs are preceded by "_admin/"


    #url(r'load-class-list/$', views.load_class_list, name='admin-load-class-list'),


    url(r'generate-questions/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', views.generate_questions, name='admin-generate-questions'),

    url(r'load-from-template/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/', views.load_question_templates, name='admin-load-question-templates'),

    url(r'fix_questions/', views.fix_questions)

)