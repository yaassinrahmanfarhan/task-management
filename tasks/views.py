from django.shortcuts import render, redirect
from django.http import HttpResponse
from tasks.forms import TaskForm, TaskModelForm, TaskDetailModelForm
from tasks.models import Task, TaskDetail, Project
from datetime import date
from django.db.models import Q, Count, Max, Min, Avg
from django.contrib import messages
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.views.generic.base import ContextMixin
from django.views.generic import ListView, DetailView, UpdateView


# Class Based View Re-use example
class Greetings(View):
    greetings = 'Hello Everyone'

    def get(self, request):
        return HttpResponse(self.greetings)


class HiGreetings(Greetings):
    greetings = 'Hi Everyone'


class HiHowGreetings(Greetings):
    greetings = 'Hi Everyone, How are you'


def is_manager(user):
    return user.groups.filter(name='Manager').exists()


def is_employee(user):
    return user.groups.filter(name='Employee').exists()


def is_admin(user):
    return user.groups.filter(name='Admin').exists()


class ManagerDashboardView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'no-permission'

    def test_func(self):
        return is_manager(self.request.user)

    def get(self, request, *args, **kwargs):
        task_type = request.GET.get('type', 'all')

        counts = Task.objects.aggregate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='COMPLETED')),
            in_progress=Count('id', filter=Q(status='IN_PROGRESS')),
            pending=Count('id', filter=Q(status='PENDING')),
        )

        base_query = Task.objects.select_related('details').prefetch_related('assigned_to')

        if task_type == 'completed':
            tasks = base_query.filter(status='COMPLETED')
        elif task_type == 'in-progress':
            tasks = base_query.filter(status='IN_PROGRESS')
        elif task_type == 'pending':
            tasks = base_query.filter(status='PENDING')
        else:
            tasks = base_query.all()

        context = {
            "tasks": tasks,
            "counts": counts,
            "role": 'manager'
        }
        return render(request, "dashboard/manager-dashboard.html", context)


class EmployeeDashboardView(LoginRequiredMixin, UserPassesTestMixin, View):
    login_url = 'no-permission'

    def test_func(self):
        return is_employee(self.request.user)

    def get(self, request, *args, **kwargs):
        return render(request, "dashboard/user-dashboard.html")


class CreateTask(ContextMixin, LoginRequiredMixin, PermissionRequiredMixin, View):
    """ For creating task """
    permission_required = 'tasks.add_task'
    login_url = 'sign-in'
    template_name = 'task_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['task_form'] = kwargs.get('task_form', TaskModelForm())
        context['task_detail_form'] = kwargs.get('task_detail_form', TaskDetailModelForm())
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        task_form = TaskModelForm(request.POST)
        task_detail_form = TaskDetailModelForm(request.POST, request.FILES)

        if task_form.is_valid() and task_detail_form.is_valid():
            task = task_form.save()
            task_detail = task_detail_form.save(commit=False)
            task_detail.task = task
            task_detail.save()

            messages.success(request, "Task Created Successfully")
        return render(request, self.template_name, self.get_context_data())


class UpdateTask(UpdateView):
    model = Task
    form_class = TaskModelForm
    template_name = 'task_form.html'
    context_object_name = 'task'
    pk_url_kwarg = 'id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['task_form'] = self.get_form()
        if hasattr(self.object, 'details') and self.object.details:
            context['task_detail_form'] = TaskDetailModelForm(instance=self.object.details)
        else:
            context['task_detail_form'] = TaskDetailModelForm()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        task_form = TaskModelForm(request.POST, instance=self.object)
        task_detail_form = TaskDetailModelForm(
            request.POST, request.FILES, instance=getattr(self.object, 'details', None)
        )

        if task_form.is_valid() and task_detail_form.is_valid():
            task = task_form.save()
            task_detail = task_detail_form.save(commit=False)
            task_detail.task = task
            task_detail.save()

            messages.success(request, "Task Updated Successfully")
        return redirect('update-task', self.object.id)


class DeleteTaskView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'tasks.delete_task'
    login_url = 'no-permission'

    def post(self, request, id, *args, **kwargs):
        try:
            task = Task.objects.get(id=id)
            task.delete()
            messages.success(request, 'Task Deleted Successfully')
        except Task.DoesNotExist:
            messages.error(request, 'Something went wrong')
        return redirect('manager-dashboard')

    def get(self, request, id, *args, **kwargs):
        messages.error(request, 'Something went wrong')
        return redirect('manager-dashboard')


class ViewTaskView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'tasks.view_task'
    login_url = 'no-permission'

    def get(self, request, *args, **kwargs):
        projects = Project.objects.annotate(
            num_task=Count('task')
        ).order_by('num_task')
        return render(request, "show_task.html", {"projects": projects})


class ViewProject(ListView):
    model = Project
    context_object_name = 'projects'
    template_name = 'show_task.html'

    def get_queryset(self):
        queryset = Project.objects.annotate(
            num_task=Count('task')
        ).order_by('num_task')
        return queryset


class TaskDetail(DetailView):
    model = Task
    template_name = 'task_details.html'
    context_object_name = 'task'
    pk_url_kwarg = 'task_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Task.STATUS_CHOICES
        return context

    def post(self, request, *args, **kwargs):
        task = self.get_object()
        selected_status = request.POST.get('task_status')
        task.status = selected_status
        task.save()
        return redirect('task-details', task.id)


class DashboardRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if is_manager(request.user):
            return redirect('manager-dashboard')
        elif is_employee(request.user):
            return redirect('user-dashboard')
        elif is_admin(request.user):
            return redirect('admin-dashboard')
        return redirect('no-permission')
