"""
Create (or reset) a member account.

    python manage.py create_member mohitg2 --password "..." --email mohitg2@illinois.edu

The password is read from --password, then from the MEMBER_PASSWORD environment variable, otherwise it is asked for.
Running it again for an existing username resets the password, so it is safe to repeat on a new server.
"""

import getpass
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from trips.models import Traveler


class Command(BaseCommand):
    help = "Create a member account (or reset the password of an existing one)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password", help="Defaults to $MEMBER_PASSWORD, otherwise you are asked.")
        parser.add_argument("--email", default="")

    def handle(self, *args, **opts):
        password = opts["password"] or os.environ.get("MEMBER_PASSWORD") or getpass.getpass("Password: ")
        if not password:
            raise CommandError("A password is required.")
        user, created = User.objects.get_or_create(username=opts["username"], defaults={"email": opts["email"]})
        if opts["email"]:
            user.email = opts["email"]
        user.set_password(password)
        user.save()
        Traveler.for_user(user)
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} member {user.username}."))
