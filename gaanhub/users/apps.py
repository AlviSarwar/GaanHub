from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'
    default_auto_field = 'django.db.models.BigAutoField'
    verbose_name = 'Users'

    def ready(self):
        # Register signal handlers so UserProfile is auto-created for all new users
        import users.signals  # noqa: F401
