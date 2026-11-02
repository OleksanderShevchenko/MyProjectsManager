from django.db import migrations


def backfill_orphan_timelog_timesheets(apps, schema_editor):
    """
    Backfill any orphaned TimeLog records that don't have a linked WeeklyTimesheet.
    Derives year and ISO week number from TimeLog.date and assigns or creates
    the corresponding WeeklyTimesheet.
    """
    TimeLog = apps.get_model('work_time_reporter', 'TimeLog')
    WeeklyTimesheet = apps.get_model('work_time_reporter', 'WeeklyTimesheet')

    for log in TimeLog.objects.filter(timesheet__isnull=True):
        year, week_number, _ = log.date.isocalendar()
        timesheet, _ = WeeklyTimesheet.objects.get_or_create(
            user=log.user,
            year=year,
            week_number=week_number,
            defaults={'status': 'DRAFT'}
        )
        log.timesheet = timesheet
        log.save(update_fields=['timesheet'])


def reverse_backfill(apps, schema_editor):
    # No-op reverse migration
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('work_time_reporter', '0006_companycalendar_created_at_and_more'),
    ]

    operations = [
        migrations.RunPython(
            backfill_orphan_timelog_timesheets,
            reverse_code=reverse_backfill,
        ),
    ]
