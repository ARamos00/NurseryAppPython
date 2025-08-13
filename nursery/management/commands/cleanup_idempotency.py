from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Prune old IdempotencyKey records (default: older than 24 hours)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Delete idempotency records older than this many hours (default 24).",
        )

    def handle(self, *args, **options):
        try:
            Model = apps.get_model("core", "IdempotencyKey")
        except LookupError:
            self.stdout.write(self.style.WARNING("IdempotencyKey model not found; nothing to clean."))
            return

        cutoff = timezone.now() - timedelta(hours=int(options["hours"]))
        qs = Model.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} idempotency records older than {options['hours']}h."))
