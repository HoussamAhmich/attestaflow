from django.db import models
from django.contrib.auth.models import User
import uuid

class Utilisateur(models.Model):
    ROLE_CHOICES = [('beneficiaire','Bénéficiaire'),('agent','Agent Administratif'),('admin','Administrateur')]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nom = models.CharField(max_length=100)
    email = models.EmailField()
    mot_de_passe = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='beneficiaire')
    def __str__(self): return f"{self.nom} ({self.role})"

class Demande(models.Model):
    STATUT_CHOICES = [('en attente','En attente'),('acceptée','Acceptée'),('refusée','Refusée')]
    type_document = models.CharField(max_length=100, default='Attestation de scolarité')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en attente')
    date_soumission = models.DateTimeField(auto_now_add=True)
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE)
    cin = models.CharField(max_length=20, blank=True, default='')
    date_naissance = models.CharField(max_length=20, blank=True, default='')
    lieu_naissance = models.CharField(max_length=100, blank=True, default='')
    filiere = models.CharField(max_length=100, blank=True, default='')
    niveau = models.CharField(max_length=50, blank=True, default='')
    annee_universitaire = models.CharField(max_length=20, blank=True, default='')
    matricule = models.CharField(max_length=50, blank=True, default='')
    motif_refus = models.CharField(max_length=500, blank=True, null=True)
    def __str__(self): return f"{self.type_document} - {self.statut}"

class Attestation(models.Model):
    STATUT_CHOICES = [('valide','Valide'),('annulee','Annulée')]
    demande = models.OneToOneField(Demande, on_delete=models.CASCADE)
    numero = models.UUIDField(default=uuid.uuid4, unique=True)
    date_emission = models.DateField(auto_now_add=True, null=True, blank=True)
    qr_code = models.ImageField(upload_to='qrcodes/', blank=True)
    pdf = models.FileField(upload_to='attestations/', blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='valide')
    def __str__(self): return str(self.numero)

class EtudiantDB(models.Model):
    matricule = models.CharField(max_length=50, primary_key=True, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    cin = models.CharField(max_length=20)
    date_naissance = models.CharField(max_length=20)
    lieu_naissance = models.CharField(max_length=100)
    filiere = models.CharField(max_length=100)
    niveau = models.CharField(max_length=50)
    annee_universitaire = models.CharField(max_length=20)
    annee_debut = models.CharField(max_length=10)
    annee_fin = models.CharField(max_length=10)
    nationalite = models.CharField(max_length=50, default='Marocaine')
    def __str__(self): return f"{self.prenom} {self.nom} ({self.matricule})"

class JournalAction(models.Model):
    ACTION_CHOICES = [('connexion','Connexion'),('deconnexion','Déconnexion'),('validation','Validation'),('rejet','Rejet'),('generation_pdf','PDF'),('soumission','Soumission'),('register','Inscription')]
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    detail = models.TextField(blank=True, default='')
    date_action = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.utilisateur} — {self.action} — {self.date_action}"
    class Meta: ordering = ['-date_action']