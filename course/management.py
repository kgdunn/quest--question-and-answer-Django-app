# Code from  Marty Alchin's book: Pro Django, page 82.
from django.db.models import signals

def create_blank_course(app, created_models, verbosity, **kwargs):
    """
    Automatically create a new course, "No course" after ``syncdb``.
    """
    app_label = app.__name__.split('.')[-2]

    if app_label == 'course':
        from course.models import Course
        Course.objects.get_or_create(name="Empty (blank) course",
                                     code="---")

signals.post_syncdb.connect(create_blank_course)
