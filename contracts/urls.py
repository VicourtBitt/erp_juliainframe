from django.urls import path

from . import views

app_name = "contracts"

urlpatterns = [
    path("criador/", views.creator, name="creator"),
    path("gerados/", views.generated_list, name="generated_list"),
    path("gerados/<int:pk>/", views.generated_detail, name="generated_detail"),
    path("gerados/<int:pk>/preview/", views.generated_preview, name="generated_preview"),
    path("gerados/<int:pk>/html/", views.generated_edit_html, name="generated_edit_html"),
    path("gerados/<int:pk>/download/<str:fmt>/", views.generated_download, name="generated_download"),
    path("gerados/<int:pk>/arquivar/", views.generated_archive, name="generated_archive"),
    path("gerados/<int:pk>/apagar/", views.generated_delete, name="generated_delete"),
    path("modelos/", views.template_list, name="templates"),
    path("modelos/<int:pk>/editar/", views.template_edit, name="template_edit"),
    path("modelos/<int:pk>/apagar/", views.template_delete, name="template_delete"),
    path("arquivo/", views.archive, name="archive"),
    path("arquivo/<int:pk>/", views.archive_preview, name="archive_preview"),
    path("arquivo/<int:pk>/arquivo/", views.archive_file, name="archive_file"),
    path("arquivo/<int:pk>/editar/", views.archive_edit, name="archive_edit"),
    path("arquivo/<int:pk>/apagar/", views.archive_delete, name="archive_delete"),
    path("assinaturas/", views.signatures, name="signatures"),
]
