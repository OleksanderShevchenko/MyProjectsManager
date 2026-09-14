import logging
from functools import wraps
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


def manager_required(view_func):
    """
    Decorator for views that requires the user to be an active manager of at least one project,
    a member of the 'Project Manager' group, or a superuser.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            logger.warning("Unauthenticated access attempt to manager view '%s'", view_func.__name__)
            return redirect('work_time_reporter:login')

        is_manager = (
            request.user.is_superuser
            or getattr(request.user, 'is_active_manager', False)
            or request.user.groups.filter(name='Project Manager').exists()
        )
        if not is_manager:
            logger.warning(
                "Unauthorized access to manager view '%s' denied for user %s",
                view_func.__name__,
                request.user.username,
            )
            messages.warning(request, "Access denied. You are not a manager of any active project.")
            return redirect('work_time_reporter:dashboard')

        return view_func(request, *args, **kwargs)

    return wrapper


def admin_required(view_func):
    """
    Decorator for views that requires the user to have administrative privileges
    (superuser or member of 'Admin' group).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            logger.warning("Unauthenticated access attempt to admin view '%s'", view_func.__name__)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
            return redirect('work_time_reporter:login')

        is_admin = (
            request.user.is_superuser
            or getattr(request.user, 'is_admin_role', False)
            or request.user.groups.filter(name='Admin').exists()
        )
        if not is_admin:
            logger.warning(
                "Unauthorized access to admin view '%s' denied for user %s",
                view_func.__name__,
                request.user.username,
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
            messages.error(request, "Access denied. Administrator privileges required.")
            return redirect('work_time_reporter:dashboard')

        return view_func(request, *args, **kwargs)

    return wrapper
