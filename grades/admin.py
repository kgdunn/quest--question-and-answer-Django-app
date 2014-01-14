from django.contrib import admin
from models import Grade

class GradeAdmin(admin.ModelAdmin):
    list_display = ('id', 'grade_value',  'reason_description')
    list_display_links = ('grade_value', 'reason_description')
    list_per_page = 1000
    ordering = ('-id',)


admin.site.register(Grade, GradeAdmin)



from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
UserAdmin.list_per_page = 1000
UserAdmin.list_display = ('username', 'is_active', 'is_staff', 'is_superuser', 'date_joined', 'last_login')
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
