from django.contrib import admin
from models import Grade

class GradeAdmin(admin.ModelAdmin):
    list_display = ('id', 'grade_value',  'reason_description')
    list_display_links = ('grade_value', 'reason_description')
    list_per_page = 1000
    ordering = ('-id',)


admin.site.register(Grade, GradeAdmin)