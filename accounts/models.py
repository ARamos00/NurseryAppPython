from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """
    Project's custom user model.
    Keeping Django defaults for now; extend with fields later as needed.
    """
    pass
