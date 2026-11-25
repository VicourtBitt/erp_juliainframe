from django.urls import path

from . import views

app_name = "receipts"

urlpatterns = [
    path("", views.receipt_list, name="list"),
    path("novo/", views.receipt_form, name="create"),
    path("<int:pk>/", views.receipt_detail, name="detail"),
    path("<int:pk>/editar/", views.receipt_form, name="edit"),
    path("<int:pk>/pdf/", views.receipt_pdf, name="pdf"),
    path("<int:pk>/apagar/", views.receipt_delete, name="delete"),
]
