"""Bill a student as soon as they are enrolled (scope: "a new student in that
class shows all 4 dues"). Runs synchronously inside the enrolment's own
transaction, so an enrolment and its charges commit or roll back together.

This is the one place Fees listens to another app instead of being called:
`apps.people` must not import `apps.fees` (people is the lower layer)."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.people.models import Enrollment


@receiver(post_save, sender=Enrollment, dispatch_uid="fees_bill_new_enrollment")
def bill_new_enrollment(sender, instance: Enrollment, created: bool, raw: bool = False, **kwargs):
    if created and not raw and instance.status == Enrollment.Status.ACTIVE:
        from apps.fees.services import apply_plans_for_enrollment

        apply_plans_for_enrollment(instance)
