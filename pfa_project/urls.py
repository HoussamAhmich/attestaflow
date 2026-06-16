from django.contrib import admin
from django.urls import path
from gestion import views
from django.conf import settings
from django.conf.urls.static import static

handler404 = 'gestion.views.page_404'
handler403 = 'gestion.views.page_403'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home),
    path('login/', views.login_view),
    path('logout/', views.logout_view),
    path('register/', views.register),
    path('dashboard/', views.dashboard),
    path('demande/', views.ajouter_demande),
    path('annuler/<int:demande_id>/', views.annuler_attestation, name='annuler_attestation'),
    path('liste/', views.liste_demandes),
    path('journal/', views.journal_actions, name='journal'),
    path('accepter/<int:id>/', views.accepter_demande),
    path('attestation/<int:demande_id>/pdf/', views.generer_attestation_pdf),
    path('admin-stats/', views.admin_stats),
    path('admin-users/', views.admin_users),
    path('admin-demandes/', views.admin_demandes),
    path('admin-attestations/', views.admin_attestations),
    path('admin-change-role/<int:user_id>/', views.admin_change_role),
    path('mes-attestations/', views.mes_attestations),
    path('profil/', views.profil),
    path('verifier-page/', views.verifier_page),
    path('aide/', views.aide),
    path('parametres/', views.parametres),
    path('changer-password/', views.changer_password),
    path('verifier/<str:numero>/', views.verifier_public),
    path('verifier-matricule/<str:matricule>/', views.verifier_matricule),
    path('admin-supprimer-user/<int:user_id>/', views.supprimer_utilisateur),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'gestion' / 'static')