from django.contrib import admin
from models import User, UserProfile, Token, Timing, Group
from django.db.models import signals

# Create a ``UserProfile`` for every user
import views
signals.post_save.connect(views.create_new_account, User)

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'role')
    list_display_links = ('user',)
    list_per_page = 1000
    ordering = ('user',)
admin.site.register(UserProfile, UserProfileAdmin)

class GroupAdmin(admin.ModelAdmin):
    list_display = ('pk', 'name', )
    list_display_links = ('name',)
    list_per_page = 1000
    ordering = ('name',)
admin.site.register(Group, GroupAdmin)


class TokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'token_address', 'has_been_used')
    list_display_links = ('user', 'token_address')
    list_per_page = 1000
    ordering = ('-id',)
admin.site.register(Token, TokenAdmin)


class TimingAdmin(admin.ModelAdmin):
    list_display = ('id', 'start_time', 'final_time', 'qset', 'token')
    list_display_links = ('start_time', 'final_time')
    list_per_page = 1000
    ordering = ('-id',)
admin.site.register(Timing, TimingAdmin)




