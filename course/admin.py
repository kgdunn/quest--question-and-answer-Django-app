from django.contrib import admin
from models import Course

class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code', 'year', 'slug')
    list_display_links = ('name', 'code')
    list_per_page = 1000
    ordering = ('id',)

admin.site.register(Course, CourseAdmin)