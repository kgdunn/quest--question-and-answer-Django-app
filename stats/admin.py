from django.contrib import admin
from stats.models import PageHit, Profile, TimerStart

class PageHitAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'ip_address', 'item', 'item_pk', 'profile',
                    'extra_info', 'user_id')
    list_per_page = 1000
admin.site.register(PageHit, PageHitAdmin)


class ProfileAdmin(admin.ModelAdmin):
    list_display = ('datetime', 'hashid', 'ua_string', 'os', 'software',
                    'display')
    list_per_page = 1000
admin.site.register(Profile, ProfileAdmin)


class TimerStartAdmin(admin.ModelAdmin):
    list_display =('time', 'user', 'event', 'profile', 'item_pk',
                   'item_type', 'other_info')
    list_per_page = 5000


admin.site.register(TimerStart, TimerStartAdmin)
