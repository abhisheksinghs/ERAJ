"""
Who can do what (ADR-006). The single source of truth for permissions; the
frontend receives the same patterns from `/api/auth/me` and evaluates them the
same way.

Permission names are `<module>.<resource>.<verb>`. ViewSets declare a
`perm_resource` (e.g. "library.issue"); safe methods need `<resource>.view`,
writes need `<resource>.manage`, and workflow actions declare their own name
(e.g. "library.fine.waive") in `action_perms`.

Patterns: `*` matches within and across segments (fnmatch). A pattern starting
with `-` denies, and a deny beats any allow held by the same role.
"""
from __future__ import annotations

from fnmatch import fnmatchcase

from apps.org.models import Role

# Read-only access to the shared registry that most staff roles need in order
# to pick a student, staff member or class in their own module. (Branch names
# for the switcher come from /api/auth/me, so staff roles get no Settings screen.)
REGISTRY_READ = ["people.*.view"]

PERMISSIONS: dict[str, list[str]] = {
    # A branch admin runs their branch; creating branches and assigning the
    # group-admin role is for the group admin (the client owner gets both).
    Role.ADMIN: ["*", "-org.branch.manage", "-org.group_admin.assign"],
    Role.GROUP_ADMIN: ["*"],
    Role.ACCOUNTANT: [
        *REGISTRY_READ,
        "fees.*",
        "-fees.receipt.cancel",
        "-fees.concession.approve",
        "payroll.*",
        "-payroll.run.reverse",
        "hostel.mess*.view",
        "transport.*.view",
        "reports.*",
    ],
    Role.TEACHER: [
        *REGISTRY_READ,
        "attendance.*",
        "-attendance.record.correct_past",
        "exam.*",
        "-exam.marks.unlock",
        "-exam.setup.manage",
        "timetable.*.view",
        "learning.*",
        "library.*.view",
    ],
    Role.LIBRARIAN: [*REGISTRY_READ, "library.*", "-library.fine.waive"],
    Role.WARDEN: [*REGISTRY_READ, "hostel.*", "fees.*.view"],
    Role.TRANSPORT: [*REGISTRY_READ, "transport.*", "fees.*.view"],
    Role.HR: [*REGISTRY_READ, "people.staff.*", "people.department.*", "hr.*", "payroll.*.view"],
    Role.STORE: [*REGISTRY_READ, "inventory.*", "-inventory.stock.adjust", "-inventory.requisition.approve"],
    # Portal roles: their querysets are restricted to their own children/self
    # in the portal API; these patterns only open the portal endpoints.
    Role.PARENT: ["portal.*"],
    Role.STUDENT: ["portal.*"],
}


def role_allows(role: str, perm: str) -> bool:
    patterns = PERMISSIONS.get(role, [])
    if any(p.startswith("-") and fnmatchcase(perm, p[1:]) for p in patterns):
        return False
    return any(not p.startswith("-") and fnmatchcase(perm, p) for p in patterns)


def roles_allow(roles: set[str], perm: str) -> bool:
    return any(role_allows(r, perm) for r in roles)
