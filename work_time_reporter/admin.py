from django.contrib import admin
from django.db.models import Count, Sum
from django.urls import reverse
from django.utils.html import format_html
from .models import Project, Task, TimeLog, WeeklyTimesheet, CompanyCalendar


# Allows viewing and modifying tasks directly inside a project
class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ('title', 'status', 'budget_hours', 'deadline')
    show_change_link = True


# Allows viewing all logged hours directly inside a task
class TaskTimeLogInLine(admin.TabularInline):
    model = TimeLog
    extra = 0
    fields = ('user', 'date', 'hours', 'timesheet', 'comment')
    readonly_fields = ('user', 'date', 'hours', 'timesheet', 'comment')
    can_delete = True
    show_change_link = True


# Allows you to see and edit logs directly inside the weekly report
class TimeLogInline(admin.TabularInline):
    model = TimeLog
    extra = 0
    fields = ('task', 'date', 'hours', 'comment')
    autocomplete_fields = ('task',)


@admin.register(CompanyCalendar)
class CompanyCalendarAdmin(admin.ModelAdmin):
    list_display = ('date', 'day_type', 'description')
    list_filter = ('day_type',)
    date_hierarchy = 'date'


@admin.register(WeeklyTimesheet)
class WeeklyTimesheetAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'week_number', 'status', 'total_hours_display', 'logs_count_display')
    list_filter = ('status', 'year', 'user')
    search_fields = ('user__username', 'week_number')
    autocomplete_fields = ('user',)
    inlines = [TimeLogInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user').annotate(
            total_hours=Sum('time_logs__hours'),
            logs_count=Count('time_logs', distinct=True),
        )

    @admin.display(description="Total Hours", ordering="total_hours")
    def total_hours_display(self, obj):
        return f"{float(obj.total_hours or 0):.1f}h"

    @admin.display(description="Logs Count", ordering="logs_count")
    def logs_count_display(self, obj):
        return f"{obj.logs_count} logs"

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
    list_display = ('name', 'project_type', 'manager', 'year', 'is_active', 'tasks_count_display')
    # Sidebar with filters (very convenient to search for active projects of the desired year)
    list_filter = ('project_type', 'is_active', 'year', 'manager')
    # Search field by name
    search_fields = ('name',)
    # add convenient interface for selecting user
    filter_horizontal = ('members',)
    inlines = [TaskInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            tasks_count=Count('tasks', distinct=True),
        )

    @admin.display(description="Tasks", ordering="tasks_count")
    def tasks_count_display(self, obj):
        url = reverse('admin:work_time_reporter_task_changelist') + f'?project__id__exact={obj.id}'
        return format_html('<a href="{}">{} tasks ➔</a>', url, obj.tasks_count)

    class Media:
        css = {
            'all': ('admin/custom_admin.css',)  # The path starts from the 'static' folder
        }


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project_link', 'budget_hours', 'spent_display', 'deadline', 'status')
    list_filter = ('status', 'project__project_type', 'project__is_active', 'project__year', 'project')
    search_fields = ('title', 'project__name')
    # add convenient interface for selecting user
    filter_horizontal = ('assignees',)
    autocomplete_fields = ('project',)
    inlines = [TaskTimeLogInLine]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('project').annotate(
            spent_hours=Sum('time_logs__hours'),
        )

    @admin.display(description="Project", ordering="project__name")
    def project_link(self, obj):
        url = reverse('admin:work_time_reporter_project_change', args=[obj.project_id])
        return format_html('<a href="{}">📂 {}</a>', url, obj.project.name)

    @admin.display(description="Spent", ordering="spent_hours")
    def spent_display(self, obj):
        spent = float(obj.spent_hours or 0)
        budget = float(obj.budget_hours or 0)
        if budget > 0:
            pct = (spent / budget) * 100
            color = "#dc2626" if spent > budget else "#16a34a"
            return format_html('<span style="color: {}; font-weight: 600;">{:.1f}h ({:.0f}%)</span>', color, spent, pct)
        return f"{spent:.1f}h"

    class Media:
        css = {
            'all': ('admin/custom_admin.css',)  # The path starts from the 'static' folder
        }


@admin.register(TimeLog)
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'project_link', 'task_link', 'hours', 'timesheet_link', 'comment')
    list_filter = ('task__project', 'user', 'timesheet__status', 'date')
    search_fields = ('task__title', 'task__project__name', 'user__username', 'comment')
    date_hierarchy = 'date'
    autocomplete_fields = ('task', 'user', 'timesheet')
    list_select_related = ('task', 'task__project', 'user', 'timesheet')

    @admin.display(description="Project", ordering="task__project__name")
    def project_link(self, obj):
        url = reverse('admin:work_time_reporter_project_change', args=[obj.task.project_id])
        return format_html('<a href="{}">📂 {}</a>', url, obj.task.project.name)

    @admin.display(description="Task", ordering="task__title")
    def task_link(self, obj):
        url = reverse('admin:work_time_reporter_task_change', args=[obj.task_id])
        return format_html('<a href="{}">{}</a>', url, obj.task.title)

    @admin.display(description="Timesheet", ordering="timesheet__year")
    def timesheet_link(self, obj):
        url = reverse('admin:work_time_reporter_weeklytimesheet_change', args=[obj.timesheet_id])
        status = obj.timesheet.status
        status_color = "#16a34a" if status == "APPROVED" else ("#d97706" if status == "SUBMITTED" else "#6b7280")
        return format_html(
            '<a href="{}">{} W{:02d} <span style="color: {}; font-weight: 600;">[{}]</span></a>',
            url, obj.timesheet.year, obj.timesheet.week_number, status_color, status
        )
