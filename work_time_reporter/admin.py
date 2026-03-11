from django.contrib import admin
from .models import Project, Task, TimeLog

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # Columns that will be displayed in the project list
    list_display = ('name', 'project_type', 'year', 'is_active')
    # Sidebar with filters (very convenient to search for active projects of the desired year)
    list_filter = ('project_type', 'is_active', 'year')
    # Search field by name
    search_fields = ('name',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'budget_hours', 'deadline', 'status')
    list_filter = ('status', 'project')
    search_fields = ('title',)

@admin.register(TimeLog)
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'date', 'hours')
    list_filter = ('date', 'user')
    search_fields = ('task__title', 'comment')