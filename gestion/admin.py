from django.contrib import admin
from .models import Utilisateur, Demande, Attestation, JournalAction

admin.site.register(Utilisateur)
admin.site.register(Demande)
admin.site.register(Attestation)
admin.site.register(JournalAction)