from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.
class CustomUser(AbstractUser):
    # Here we will add new fields for a user
    # for example: bio = models.TextField(blank=True)
    pass