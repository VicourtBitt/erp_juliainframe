from django.urls import path

from . import views

app_name = "finance"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("auditoria/", views.audit, name="audit"),
    path("transacoes/<int:pk>/", views.transaction_detail, name="transaction_detail"),
    path("transacoes/<int:pk>/editar/", views.transaction_edit, name="transaction_edit"),
    path("transacoes/<int:pk>/apagar/", views.transaction_delete, name="transaction_delete"),
    path("parcelas/<int:pk>/status/", views.installment_set_status, name="installment_status"),
    path("parcelas/pagar-mes/", views.installments_pay_month, name="installments_pay_month"),
    path("categorias/", views.categories, name="categories"),
    path("categorias/<int:pk>/editar/", views.category_edit, name="category_edit"),
    path("categorias/<int:pk>/apagar/", views.category_delete, name="category_delete"),
]
