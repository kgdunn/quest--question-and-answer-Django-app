from django.contrib import admin
from models import QSet, QTemplate

class QTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)
    list_display_links = ('name', )
    list_per_page = 1000
    ordering = ('id',)

class QSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'min_total', 'max_total', 'course')
    list_display_links = ('name', )
    list_per_page = 1000
    ordering = ('id',)

admin.site.register(QTemplate, QTemplateAdmin)
admin.site.register(QSet, QSetAdmin)

