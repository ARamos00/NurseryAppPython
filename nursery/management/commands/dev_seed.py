from __future__ import annotations

"""
Seed development data for the Nursery app.

Goals
-----
- Fast local onboarding with realistic yet deterministic sample data.
- Idempotent-ish: Uses `get_or_create` and targeted updates so re-running keeps
  data consistent without creating duplicates.

What it creates
---------------
- Two users ("alice", "bob") with known passwords for local testing.
- A set of Taxa, PlantMaterials, PropagationBatches, Plants, and Events with
  sensible relationships and varied statuses/methods.
- Size profiles (SMALL|MEDIUM|LARGE) to scale volume.

Safety
------
- `--reset` option hard-deletes existing nursery data across all users (be careful).
- Command wraps the main `handle` in `@transaction.atomic` to keep partial runs
  from leaving inconsistent state.

Usage
-----
    python manage.py dev_seed --size MEDIUM
    python manage.py dev_seed --reset --size SMALL
"""

from dataclasses import dataclass
from typing import Iterable, Tuple
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from nursery.models import (
    Taxon,
    PlantMaterial,
    PropagationBatch,
    Plant,
    Event,
    MaterialType,
    PropagationMethod,
    BatchStatus,
    PlantStatus,
    EventType,
)

User = get_user_model()


@dataclass(frozen=True)
class SizeProfile:
    """Relative scale factors for generated data (baseline is 'SMALL')."""
    taxon_mult: int
    material_per_taxon: int
    batches_per_material: int
    plants_per_batch: int
    events_per_batch: int


SIZES = {
    "SMALL": SizeProfile(taxon_mult=1, material_per_taxon=1, batches_per_material=1, plants_per_batch=1, events_per_batch=5),
    "MEDIUM": SizeProfile(taxon_mult=2, material_per_taxon=2, batches_per_material=2, plants_per_batch=2, events_per_batch=8),
    "LARGE": SizeProfile(taxon_mult=4, material_per_taxon=2, batches_per_material=3, plants_per_batch=3, events_per_batch=12),
}


class Command(BaseCommand):
    """
    Seed deterministic development data for quick demos and tests.

    Options:
        --reset  : delete existing nursery data before creating new sample data
        --size   : SMALL (default), MEDIUM, LARGE
    """
    help = "Seed development data (idempotent). Use --reset to clear existing nursery data first."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register CLI options."""
        parser.add_argument(
            "--reset",
            action="store_true",
            default=False,
            help="Delete existing nursery data for all users before seeding.",
        )
        parser.add_argument(
            "--size",
            type=str,
            choices=("SMALL", "MEDIUM", "LARGE"),
            default="SMALL",
            help="How much data to create.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        """
        Main entrypoint.

        Steps:
            - Optionally reset existing data.
            - Ensure users and set known passwords.
            - Generate taxa/materials/batches/plants/events per size profile.

        NOTE:
            Uses consistent date math so data looks plausible and queries aggregate
            meaningfully (e.g., monotonic `happened_at` within a timeline).
        """
        size_key: str = options["size"].upper()
        profile: SizeProfile = SIZES[size_key]

        if options["reset"]:
            self._reset()

        alice, bob = self._ensure_users()
        self.stdout.write(self.style.SUCCESS(f"Users ready: {alice.username}, {bob.username}"))

        # Seed each user independently
        for user, base_suffix in [(alice, "A"), (bob, "B")]:
            self._seed_for_user(user, profile, base_suffix)

        self.stdout.write(self.style.SUCCESS("Seeding complete."))

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _reset(self) -> None:
        """
        Delete existing nursery data in dependency order.

        WHY:
            Respect FK cascade order: Event -> Plant/Batch -> Material -> Taxon,
            to avoid foreign key constraint errors during truncation.
        """
        Event.objects.all().delete()
        Plant.objects.all().delete()
        PropagationBatch.objects.all().delete()
        PlantMaterial.objects.all().delete()
        Taxon.objects.all().delete()
        self.stdout.write(self.style.WARNING("Existing nursery data deleted."))

    def _ensure_users(self) -> Tuple[User, User]:
        """
        Ensure two baseline users exist and have known credentials.

        Returns:
            (alice, bob)
        """
        alice, _ = User.objects.get_or_create(username="alice", defaults={"is_staff": True, "is_superuser": False})
        alice.set_password("pass12345")
        alice.is_staff = True
        alice.save(update_fields=["password", "is_staff"])

        bob, _ = User.objects.get_or_create(username="bob", defaults={"is_staff": False, "is_superuser": False})
        bob.set_password("pass12345")
        bob.save(update_fields=["password"])

        return alice, bob

    def _seed_for_user(self, user: User, profile: SizeProfile, suffix: str) -> None:
        """
        Create related data for a single user.

        PERF:
            Uses `get_or_create` extensively to keep the command idempotent and
            efficient on re-runs. Updates a minimal set of fields when rows exist.
        """
        # A small curated list of taxa; we'll multiply it by size profile
        base_taxa: Iterable[Tuple[str, str, str]] = [
            ("Acer palmatum", "Seiryu", ""),
            ("Acer rubrum", "October Glory", ""),
            ("Betula pendula", "", "BP-1"),
            ("Pinus thunbergii", "", ""),
            ("Quercus robur", "", ""),
            ("Camellia japonica", "Debutante", ""),
        ]

        taxa_created = []
        for i in range(profile.taxon_mult):
            for sci, cultivar, clone in base_taxa:
                # Make cultivar/clone vary slightly across multiples to avoid uniqueness collisions
                cv = f"{cultivar}-{i}" if cultivar else cultivar
                cl = f"{clone}-{i}" if clone else clone
                taxon, _ = Taxon.objects.get_or_create(
                    user=user,
                    scientific_name=sci,
                    cultivar=cv or "",
                    clone_code=cl or "",
                )
                taxa_created.append(taxon)

        # For deterministic dates/times
        today = timezone.now().date()
        now = timezone.now().replace(microsecond=0)

        materials_created = []
        for t_index, taxon in enumerate(taxa_created, start=1):
            # Keep lot codes unique and readable
            for j in range(profile.material_per_taxon):
                if j % 2 == 0:
                    mtype = MaterialType.SEED
                    lot = f"{suffix}-{t_index:02d}-SEED-{j:02d}"
                else:
                    mtype = MaterialType.CUTTING
                    lot = f"{suffix}-{t_index:02d}-CUT-{j:02d}"

                material, _ = PlantMaterial.objects.get_or_create(
                    user=user,
                    taxon=taxon,
                    material_type=mtype,
                    lot_code=lot,
                    defaults={"notes": f"{mtype} lot {lot}"},
                )
                materials_created.append(material)

        batches_created = []
        for m_index, material in enumerate(materials_created, start=1):
            for k in range(profile.batches_per_material):
                method = (
                    PropagationMethod.SEED_SOWING
                    if material.material_type == MaterialType.SEED
                    else PropagationMethod.CUTTING_ROOTING
                )
                started_on = today - timezone.timedelta(days=(m_index + k) % 10)
                qty = 8 + (m_index + k) % 12
                status = [BatchStatus.STARTED, BatchStatus.GERMINATING, BatchStatus.POTTED, BatchStatus.GROWING][
                    (m_index + k) % 4
                ]
                note = f"{material.lot_code} • {method} • {status}"

                batch, created = PropagationBatch.objects.get_or_create(
                    user=user,
                    material=material,
                    method=method,
                    started_on=started_on,
                    quantity_started=qty,
                    defaults={"status": status, "notes": note},
                )
                if not created and batch.status != status:
                    batch.status = status
                    batch.notes = note
                    batch.save(update_fields=["status", "notes"])
                batches_created.append(batch)

        plants_created = []
        for b_index, batch in enumerate(batches_created, start=1):
            for p in range(profile.plants_per_batch):
                qty = 1 + (b_index + p) % 5
                acquired_on = batch.started_on + timezone.timedelta(days=7 + (p % 5))
                pstatus = [PlantStatus.ACTIVE, PlantStatus.DORMANT, PlantStatus.SOLD, PlantStatus.ACTIVE][
                    (b_index + p) % 4
                ]
                plant, _ = Plant.objects.get_or_create(
                    user=user,
                    taxon=batch.material.taxon,
                    batch=batch,
                    acquired_on=acquired_on,
                    defaults={"status": pstatus, "quantity": qty, "notes": ""},
                )
                # If we re-run and want status/qty to reflect current calculation:
                if plant.status != pstatus or plant.quantity != qty:
                    plant.status = pstatus
                    plant.quantity = qty
                    plant.save(update_fields=["status", "quantity"])
                plants_created.append(plant)

        # Events (timeline) – attach to batches (and sometimes plants)
        for e_index, batch in enumerate(batches_created, start=1):
            # Deterministic base for this batch
            base_time = now - timezone.timedelta(days=(e_index % 14))
            timeline = self._event_timeline(profile.events_per_batch)

            for step, (etype, delta_minutes, q_delta, note) in enumerate(timeline):
                happened_at = base_time + timezone.timedelta(minutes=delta_minutes)
                # Events primarily target the batch. Occasionally attach to a plant.
                if step % 5 == 4 and plants_created:
                    # Choose a plant from this batch if available, else fall back to batch
                    plant_for_batch = next((p for p in plants_created if p.batch_id == batch.id), None)
                    if plant_for_batch:
                        Event.objects.get_or_create(
                            user=user,
                            plant=plant_for_batch,
                            batch=None,
                            event_type=etype,
                            happened_at=happened_at,
                            defaults={"notes": note, "quantity_delta": q_delta},
                        )
                        continue

                Event.objects.get_or_create(
                    user=user,
                    batch=batch,
                    plant=None,
                    event_type=etype,
                    happened_at=happened_at,
                    defaults={"notes": note, "quantity_delta": q_delta},
                )

        self.stdout.write(self.style.SUCCESS(f"Seeded for {user.username}: "
                                             f"{len(taxa_created)} taxa, "
                                             f"{len(materials_created)} materials, "
                                             f"{len(batches_created)} batches, "
                                             f"{len(plants_created)} plants."))

    def _event_timeline(self, n: int) -> Iterable[Tuple[EventType, int, int | None, str]]:
        """
        Build a repeatable sequence of (event_type, minutes_from_base, quantity_delta, note)
        of length ~n. Quantity deltas are illustrative (+germinated, -losses, etc.).

        NOTE:
            Minute offsets are strictly increasing to ensure `happened_at` stays
            monotonic for each synthetic timeline.
        """
        pattern = [
            (EventType.SOW,           0,    +5, "Sowed"),
            (EventType.WATER,        60,  None, "Watered"),
            (EventType.GERMINATE,   180,   +3, "Germination"),
            (EventType.POT_UP,      480,  None, "Potted up"),
            (EventType.NOTE,        720,  None, "Observation"),
            (EventType.PRUNE,      1080,  None, "Pruned"),
            (EventType.MOVE,       1440,  None, "Moved to shade"),
            (EventType.WATER,      1560,  None, "Watered"),
            (EventType.FERTILIZE,  1680,  None, "Fertilized"),
            (EventType.NOTE,       1800,  None, "Observation"),
        ]
        # Repeat/cycle until we have >= n
        out = []
        idx = 0
        while len(out) < n:
            etype, mins, qd, note = pattern[idx % len(pattern)]
            # Make the minute offset strictly increasing to keep happened_at monotonic
            out.append((etype, mins + (idx // len(pattern)) * 2000, qd, note))
            idx += 1
        return out[:n]
