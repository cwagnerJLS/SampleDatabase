from django.apps import AppConfig


class SamplesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'samples'

    def ready(self):
        import samples.tasks  # Import tasks to ensure they are registered