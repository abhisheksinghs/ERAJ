"""The one admin site: public schema only, TOTP-gated (django-otp).

Bootstrap for the first superadmin (no MFA device yet):
    python manage.py createsuperuser
    python manage.py addstatictoken -t <email>      # prints one-time backup codes
    # log in with a backup code, add a TOTP device in the admin, then:
    python manage.py addstatictoken -t <email> --remove
"""
from django_otp.admin import OTPAdminSite

admin_site = OTPAdminSite(name="eraj-superadmin")
