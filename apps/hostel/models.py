"""
Hostel, Mess and Gate (ADR-007). In TENANT_APPS — one copy per tenant schema;
every row is branch-owned (ADR-001). Residents and mess members are
`people.Student` / `people.Staff` rows (ADR-002).

Residence is an `Allocation` (student <-> room, with dates) so vacating keeps
history and capacity is enforced against the count of *active* allocations.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.mixins import SoftDelete, TimeStamped
from apps.org.models import BranchOwned

MONEY = {"max_digits": 10, "decimal_places": 2}
ZERO = Decimal("0.00")


class Gender(models.TextChoices):
    MALE = "male", "Boys"
    FEMALE = "female", "Girls"
    ANY = "any", "Any"


class Meal(models.TextChoices):
    BREAKFAST = "breakfast", "Breakfast"
    LUNCH = "lunch", "Lunch"
    SNACKS = "snacks", "Evening snacks"
    DINNER = "dinner", "Dinner"


# ============================================================== hostel
class Block(TimeStamped, SoftDelete, BranchOwned):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.ANY)
    warden = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("code",)
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="hostel_block_code_unique")]

    def __str__(self) -> str:
        return self.name


class Room(TimeStamped, SoftDelete, BranchOwned):
    class Type(models.TextChoices):
        SINGLE = "single", "Single"
        DOUBLE = "double", "Double"
        TRIPLE = "triple", "Triple"
        DORM = "dorm", "Dormitory"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REPAIR = "repair", "Under repair"
        CLOSED = "closed", "Closed"

    Gender = Gender

    block = models.ForeignKey(Block, on_delete=models.PROTECT, related_name="rooms")
    number = models.CharField(max_length=20)
    floor = models.SmallIntegerField(default=0)
    room_type = models.CharField(max_length=10, choices=Type.choices, default=Type.DOUBLE)
    capacity = models.PositiveSmallIntegerField(default=2)
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.ANY)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ("block__code", "floor", "number")
        constraints = [models.UniqueConstraint(fields=["block", "number"], name="hostel_room_number_unique")]

    def __str__(self) -> str:
        return f"{self.block.code}-{self.number}"

    @property
    def occupied(self) -> int:
        return self.allocations.filter(check_out_date__isnull=True).count()

    @property
    def available_beds(self) -> int:
        return max(0, self.capacity - self.occupied)

    @property
    def has_open_maintenance(self) -> bool:
        return self.maintenance_tickets.filter(status=MaintenanceTicket.Status.OPEN).exists()


class HostelFeeRule(TimeStamped, BranchOwned):
    """Monthly hostel fee. The most specific rule wins: block + room type,
    then block, then room type, then the branch-wide rule."""

    block = models.ForeignKey(Block, null=True, blank=True, on_delete=models.CASCADE, related_name="fee_rules")
    room_type = models.CharField(max_length=10, choices=Room.Type.choices, blank=True)
    monthly_amount = models.DecimalField(**MONEY)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("block__code", "room_type")
        constraints = [
            models.CheckConstraint(check=Q(monthly_amount__gt=0), name="hostel_fee_rule_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.block or 'All blocks'} / {self.room_type or 'any'}: {self.monthly_amount}"


class Allocation(TimeStamped, BranchOwned):
    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="hostel_allocations")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="allocations")
    check_in_date = models.DateField(default=timezone.localdate)
    check_out_date = models.DateField(null=True, blank=True)
    vacate_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-check_in_date",)
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(check_out_date__isnull=True),
                name="hostel_one_active_allocation_per_student",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student} @ {self.room}"

    @property
    def is_active(self) -> bool:
        return self.check_out_date is None


class Waitlist(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        OFFERED = "offered", "Offered"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="hostel_waitlist_entries")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="waitlist")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["student", "room"],
                condition=Q(status__in=["waiting", "offered"]),
                name="hostel_one_active_waitlist_entry_per_student_room",
            ),
        ]

    def __str__(self) -> str:
        return f"waitlist: {self.student} -> {self.room} ({self.status})"


class MaintenanceTicket(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="maintenance_tickets")
    summary = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    action_taken = models.CharField(max_length=255, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.room}: {self.summary} ({self.status})"


# ============================================================== mess
class Mess(TimeStamped, SoftDelete, BranchOwned):
    name = models.CharField(max_length=100)
    name_hi = models.CharField(max_length=100, blank=True)
    blocks = models.ManyToManyField(Block, blank=True, related_name="messes")
    contractor_name = models.CharField(max_length=150, blank=True)
    contractor_phone = models.CharField(max_length=20, blank=True)
    monthly_charge = models.DecimalField(**MONEY, default=ZERO)
    per_day_rate = models.DecimalField(**MONEY, default=ZERO)
    rebate_min_days = models.PositiveSmallIntegerField(default=0, help_text="0 = no rebate")
    rebate_per_day = models.DecimalField(**MONEY, default=ZERO)
    guest_meal_rate = models.DecimalField(**MONEY, default=ZERO)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "messes"

    def __str__(self) -> str:
        return self.name


class MessMealRate(TimeStamped):
    """What the institution pays the contractor per plate."""

    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name="meal_rates")
    meal = models.CharField(max_length=10, choices=Meal.choices)
    rate = models.DecimalField(**MONEY)

    class Meta:
        ordering = ("mess", "meal")
        constraints = [models.UniqueConstraint(fields=["mess", "meal"], name="hostel_mess_meal_rate_unique")]


class MenuItem(TimeStamped, BranchOwned):
    class Day(models.IntegerChoices):
        MON = 0, "Monday"
        TUE = 1, "Tuesday"
        WED = 2, "Wednesday"
        THU = 3, "Thursday"
        FRI = 4, "Friday"
        SAT = 5, "Saturday"
        SUN = 6, "Sunday"

    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name="menu")
    day = models.PositiveSmallIntegerField(choices=Day.choices)
    meal = models.CharField(max_length=10, choices=Meal.choices)
    items = models.CharField(max_length=255)
    items_hi = models.CharField(max_length=255, blank=True)
    is_veg = models.BooleanField(default=True)

    class Meta:
        ordering = ("mess", "day", "meal")
        constraints = [models.UniqueConstraint(fields=["mess", "day", "meal"], name="hostel_menu_slot_unique")]


class MessMember(TimeStamped, BranchOwned):
    class Plan(models.TextChoices):
        MONTHLY = "monthly", "Fixed monthly"
        PER_DAY = "per_day", "Per day"

    mess = models.ForeignKey(Mess, on_delete=models.PROTECT, related_name="members")
    student = models.ForeignKey("people.Student", null=True, blank=True, on_delete=models.PROTECT, related_name="mess_memberships")
    staff = models.ForeignKey("people.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="mess_memberships")
    plan = models.CharField(max_length=8, choices=Plan.choices, default=Plan.MONTHLY)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    allocation = models.ForeignKey(Allocation, null=True, blank=True, on_delete=models.SET_NULL, related_name="mess_memberships")

    class Meta:
        ordering = ("-start_date",)
        constraints = [
            models.CheckConstraint(
                check=(Q(student__isnull=False) & Q(staff__isnull=True)) | (Q(student__isnull=True) & Q(staff__isnull=False)),
                name="hostel_mess_member_student_xor_staff",
            ),
            models.UniqueConstraint(fields=["student"], condition=Q(end_date__isnull=True, student__isnull=False),
                                    name="hostel_one_open_mess_membership_per_student"),
            models.UniqueConstraint(fields=["staff"], condition=Q(end_date__isnull=True, staff__isnull=False),
                                    name="hostel_one_open_mess_membership_per_staff"),
        ]

    def __str__(self) -> str:
        return f"{self.person} @ {self.mess}"

    @property
    def person(self):
        return self.student or self.staff


class MessLeave(TimeStamped, BranchOwned):
    member = models.ForeignKey(MessMember, on_delete=models.CASCADE, related_name="leaves")
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)
    outpass = models.OneToOneField("Outpass", null=True, blank=True, on_delete=models.SET_NULL, related_name="mess_leave")

    class Meta:
        ordering = ("-from_date",)
        constraints = [models.CheckConstraint(check=Q(to_date__gte=models.F("from_date")), name="hostel_mess_leave_dates")]

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1


class MessRebate(TimeStamped, BranchOwned):
    """Rebate register: one row per qualifying leave per month, and the charge it reduced."""

    member = models.ForeignKey(MessMember, on_delete=models.CASCADE, related_name="rebates")
    leave = models.ForeignKey(MessLeave, on_delete=models.CASCADE, related_name="rebates")
    month = models.DateField(help_text="First day of the month the leave days fall in")
    days = models.PositiveSmallIntegerField()
    amount = models.DecimalField(**MONEY)
    charge = models.ForeignKey("fees.Charge", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-month",)
        constraints = [models.UniqueConstraint(fields=["leave", "month"], name="hostel_rebate_once_per_leave_month")]


class GuestMeal(TimeStamped, BranchOwned):
    member = models.ForeignKey(MessMember, on_delete=models.PROTECT, related_name="guest_meals")
    date = models.DateField(default=timezone.localdate)
    meal = models.CharField(max_length=10, choices=Meal.choices)
    count = models.PositiveSmallIntegerField(default=1)
    guest_name = models.CharField(max_length=150, blank=True)
    amount = models.DecimalField(**MONEY, default=ZERO)
    charge = models.ForeignKey("fees.Charge", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-date",)
        constraints = [models.CheckConstraint(check=Q(count__gte=1), name="hostel_guest_meal_count")]


class MealCount(TimeStamped, BranchOwned):
    """Plates actually served, recorded by the warden (used for the contractor bill)."""

    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name="meal_counts")
    date = models.DateField()
    meal = models.CharField(max_length=10, choices=Meal.choices)
    served = models.PositiveIntegerField()

    class Meta:
        ordering = ("-date", "meal")
        constraints = [models.UniqueConstraint(fields=["mess", "date", "meal"], name="hostel_meal_count_unique")]


class MessComplaint(TimeStamped, BranchOwned):
    class Category(models.TextChoices):
        QUALITY = "quality", "Food quality"
        HYGIENE = "hygiene", "Hygiene"
        TIMING = "timing", "Timing"
        QUANTITY = "quantity", "Quantity"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    mess = models.ForeignKey(Mess, on_delete=models.CASCADE, related_name="complaints")
    member = models.ForeignKey(MessMember, null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints")
    category = models.CharField(max_length=10, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    action_taken = models.CharField(max_length=255, blank=True)
    closed_by = models.CharField(max_length=255, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


# ============================================================== gate
class ApprovedVisitor(TimeStamped, SoftDelete, BranchOwned):
    student = models.ForeignKey("people.Student", on_delete=models.CASCADE, related_name="approved_visitors")
    name = models.CharField(max_length=150)
    relation = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    photo = models.ImageField(upload_to="hostel/visitors/", null=True, blank=True)

    class Meta:
        ordering = ("student", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.relation})"


class Visit(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        HELD = "held", "Waiting for warden"
        IN = "in", "Inside"
        OUT = "out", "Left"
        REFUSED = "refused", "Refused"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="visits")
    visitor = models.ForeignKey(ApprovedVisitor, null=True, blank=True, on_delete=models.SET_NULL, related_name="visits")
    name = models.CharField(max_length=150)
    relation = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    id_proof = models.CharField(max_length=100, blank=True, help_text="e.g. Aadhaar last 4 / DL number")
    purpose = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    time_in = models.DateTimeField(null=True, blank=True)
    time_out = models.DateTimeField(null=True, blank=True)
    decided_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)


class Outpass(TimeStamped, BranchOwned):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        OUT = "out", "Out"
        RETURNED = "returned", "Returned"
        CANCELLED = "cancelled", "Cancelled"

    class RequestedBy(models.TextChoices):
        PARENT = "parent", "Parent"
        STUDENT = "student", "Student"
        WARDEN = "warden", "Warden"

    student = models.ForeignKey("people.Student", on_delete=models.PROTECT, related_name="outpasses")
    from_date = models.DateField()
    to_date = models.DateField(help_text="Expected return date")
    return_by = models.TimeField(default="18:00", help_text="Expected return time on the return date")
    destination = models.CharField(max_length=200, blank=True)
    reason = models.CharField(max_length=200)
    requested_by = models.CharField(max_length=8, choices=RequestedBy.choices, default=RequestedBy.WARDEN)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    decided_by = models.CharField(max_length=255, blank=True)
    decision_note = models.CharField(max_length=200, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)

    class Meta:
        ordering = ("-from_date",)
        constraints = [models.CheckConstraint(check=Q(to_date__gte=models.F("from_date")), name="hostel_outpass_dates")]

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1
