"""Clinic hours, now per clinic. Kept as a module so existing imports work."""

import clinic_config


def is_clinic_open(clinic_id=None):
    return clinic_config.is_clinic_open(clinic_id)


def hours_message(clinic_id=None):
    return clinic_config.hours_message(clinic_id)
