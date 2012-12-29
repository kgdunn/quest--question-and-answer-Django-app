from django.contrib import admin
from models import User, UserProfile
#from django.contrib.auth.signals import user_logged_in
from django.db.models import signals

import views

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'role')
    list_display_links = ('user',)
    list_per_page = 1000
    ordering = ('user',)

admin.site.register(UserProfile, UserProfileAdmin)

# Create a ``UserProfile`` for every user
signals.post_save.connect(views.create_new_account, User)