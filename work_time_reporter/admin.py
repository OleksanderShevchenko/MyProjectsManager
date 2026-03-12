from django.contrib import admin
from .models import Project, Task, TimeLog, WeeklyTimesheet


# Allows you to see and edit logs directly inside the weekly report
class TimeLogInline(admin.TabularInline):
    model = TimeLog
    extra = 1  # Number of empty lines for new entries
    fields = ('task', 'date', 'hours', 'comment')


@admin.register(WeeklyTimesheet)
class WeeklyTimesheetAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'week_number', 'status')
    list_filter = ('status', 'year', 'user')
    search_fields = ('user__username', 'week_number')
    inlines = [TimeLogInline]

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            # If we save TimeLog from inline form
            if isinstance(instance, TimeLog):
                # Automatically assign it the same user as in the weekly report itself
                instance.user = form.instance.user
            instance.save()

        # Handle row deletion (if you click the "Delete" checkbox)
        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # Columns that will be displayed in the project list
    list_display = ('name', 'project_type', 'year', 'is_active')
    # Sidebar with filters (very convenient to search for active projects of the desired year)
    list_filter = ('project_type', 'is_active', 'year')
    # Search field by name
    search_fields = ('name',)
    # add convenient interface for selecting user
    filter_horizontal = ('members',)

    class Media:
        css = {
            'all': ('admin/custom_admin.css',)  # The path starts from the 'static' folder
        }

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'budget_hours', 'deadline', 'status')
    list_filter = ('status', 'project')
    search_fields = ('title',)
    # add convenient interface for selecting user
    filter_horizontal = ('assignees',)

    class Media:
        css = {
            'all': ('admin/custom_admin.css',)  # The path starts from the 'static' folder
        }

@admin.register(TimeLog)
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'date', 'hours')
    list_filter = ('date', 'user')
    search_fields = ('task__title', 'comment')