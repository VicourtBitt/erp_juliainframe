from django.urls import path

from . import views

app_name = "market"

urlpatterns = [
    path("", views.analyzer, name="analyzer"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/apagar/", views.delete, name="delete"),
]
