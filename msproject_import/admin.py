from django.contrib import admin

from .models import ImportBatch, StagingProject, StagingLog

class StagingProjectInline(admin.TabularInline):
    model = StagingProject
    extra = 0

class StagingLogInline(admin.TabularInline):
    model = StagingLog
    extra = 0

@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'status', 'created_at')
    list_filter = ('status', 'year', 'user')
    inlines = [StagingProjectInline, StagingLogInline]
