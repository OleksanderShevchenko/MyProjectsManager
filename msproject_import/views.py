from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import ImportBatch, StagingProject, StagingLog
from .services import fetch_pwa_data


@login_required(login_url='work_time_reporter:login')
def import_start(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        year = request.POST.get('year')

        if not email or not password or not year:
            messages.error(request, "Всі поля обов'язкові!")
            return redirect('msproject_import:start')

        try:
            # 1. Тягнемо дані через твій скрипт
            daily_data_map, unique_projects = fetch_pwa_data(email, password, int(year))

            if not daily_data_map:
                messages.warning(request, f"Даних за {year} рік не знайдено.")
                return redirect('msproject_import:start')

            # 2. Створюємо пакет (Batch)
            batch = ImportBatch.objects.create(user=request.user, year=year)

            # 3. Записуємо унікальні проєкти для розмітки
            for proj_name in unique_projects:
                StagingProject.objects.create(batch=batch, ms_project_name=proj_name)

            # 4. Записуємо всі години в сирому вигляді
            logs_to_create = []
            for date_str, items in daily_data_map.items():
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                for item in items:
                    logs_to_create.append(StagingLog(
                        batch=batch,
                        date=log_date,
                        hours=item['hours'],
                        ms_project_name=item['project'],
                        ms_task_name=item['task']
                    ))

            # bulk_create зберігає всі записи за 1 запит до бази (дуже швидко!)
            StagingLog.objects.bulk_create(logs_to_create)

            messages.success(request, f"Успішно завантажено {len(unique_projects)} проєктів. Тепер вкажіть їхні типи.")
            return redirect('msproject_import:mapping', batch_id=batch.id)

        except Exception as e:
            messages.error(request, f"Помилка імпорту: {str(e)}")
            return redirect('msproject_import:start')

    return render(request, 'msproject_import/start.html')


@login_required(login_url='work_time_reporter:login')
def import_mapping(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id, user=request.user)

    if request.method == 'POST':
        # Зберігаємо вибрані типи проєктів
        projects = batch.staged_projects.all()
        for proj in projects:
            selected_type = request.POST.get(f'project_{proj.id}')
            if selected_type:
                proj.project_type = selected_type
                proj.save()

        # Переводимо статус у PENDING (щоб побачив менеджер)
        batch.status = ImportBatch.Status.PENDING
        batch.save()

        messages.success(request, "Дані успішно відправлені менеджеру на затвердження!")
        return redirect('work_time_reporter:dashboard')

    return render(request, 'msproject_import/mapping.html', {'batch': batch})