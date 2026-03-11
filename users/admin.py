from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

# Register our custom user model in admin panel, using standard view UserAdmin
admin.site.register(CustomUser, UserAdmin)
