from __future__ import annotations

"""
Prune old idempotency records to keep the table compact.

Overview
--------
- Deletes `core.IdempotencyKey` rows older than a configurable age (default 24h).
- Safe to run as a cron/periodic job; works even when the model is absent.
- Uses app registry lookup to avoid a hard import dependency on `core`.

Usage
-----
    python manage.py cleanup_idempotency --hours 48

Notes
-----
- This command intentionally counts the rows to be deleted for an operator-friendly
  summary message before issuing the delete.
"""

from datetime import timedelta

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    """Django management command for pruning `IdempotencyKey` rows."""
    help = "Prune old IdempotencyKey records (default: older than 24 hours)."

    def add_arguments(self, parser):
        """Add the `--hours` option to control the age threshold."""
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Delete idempotency records older than this many hours (default 24).",
        )

    def handle(self, *args, **options):
        """
        Execute the cleanup.

        Steps:
            1) Resolve the model dynamically (`core.IdempotencyKey`).
            2) Compute cutoff timestamp (now - hours).
            3) Count and delete rows older than the cutoff.
        """
        try:
            Model = apps.get_model("core", "IdempotencyKey")
        except LookupError:
            # NOTE: Keep the command no-op on projects/environments that don't include the model.
            self.stdout.write(self.style.WARNING("IdempotencyKey model not found; nothing to clean."))
            return

        cutoff = timezone.now() - timedelta(hours=int(options["hours"]))
        qs = Model.objects.filter(created_at__lt=cutoff)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} idempotency records older than {options['hours']}h."))
