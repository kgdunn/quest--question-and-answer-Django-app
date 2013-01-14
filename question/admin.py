from django.contrib import admin
from models import QSet, QTemplate, QActual

class QTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)
    list_display_links = ('name', )
    list_per_page = 1000
    ordering = ('id',)

class QSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'min_total', 'max_total', 'course',
                    'ans_time_start', 'ans_time_final')
    list_display_links = ('name', )
    list_per_page = 1000
    ordering = ('id',)

class QActualAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'given_answer', 'is_submitted')
    list_display_links = ('user', )
    list_per_page = 1000
    ordering = ('id',)


admin.site.register(QTemplate, QTemplateAdmin)
admin.site.register(QSet, QSetAdmin)
admin.site.register(QActual, QActualAdmin)

