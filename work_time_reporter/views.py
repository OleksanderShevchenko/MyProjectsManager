from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Task


@login_required(login_url='/admin/login/')  # temporary use login from admin panel
def dashboard(request):
    # Searching for tasks assigned to current user (current user is in assignees list)
    user_tasks = Task.objects.filter(assignees=request.user).select_related('project')

    context = {
        'tasks': user_tasks
    }
    return render(request, 'work_time_reporter/dashboard.html', context)
