from django.conf.urls import patterns, include, url
from django.conf import settings
import views

urlpatterns = patterns('',

    # NOTE: all these URLs are preceded by "_grading/"
    #url(r'fix-glitch', views.fix_glitch),
    url(r'process-grades/(?P<course_code_slug>.+)/(?P<question_set_slug>.+)/$', views.process_grades, name='grading-process-grades'),
    url(r'process-grades/(?P<course_code_slug>.+)/$', views.grade_summary, name='grading-summary'),

)