from django.contrib import admin
from logitem.models import PageHit, Profile

class PageHitAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'ip_address', 'item', 'item_pk', 'profile',
                    'extra_info', 'user_id')
    list_per_page = 1000

class ProfileAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'hashid', 'ua_string', 'os', 'software',
                    'display')
    list_per_page = 1000


admin.site.register(PageHit, PageHitAdmin)
admin.site.register(Profile, ProfileAdmin)
