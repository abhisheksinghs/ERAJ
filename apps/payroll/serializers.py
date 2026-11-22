from decimal import Decimal

from rest_framework import serializers

from apps.org.serializers import BranchScopedSerializer, ScopedPrimaryKeyRelatedField
from apps.payroll.models import (
    DARate, Loan, OneTimePayment, PayCell, PayComponent, PayLevel, PayrollRun, PayRuleSet, Payslip, PayslipLine,
    SalaryStructure, StatutorySettings, StructureComponent,
)


class PayRuleSetSerializer(BranchScopedSerializer):
    current_da_percent = serializers.SerializerMethodField()

    class Meta:
        model = PayRuleSet
        fields = ("id", "branch", "code", "name", "hra_x", "hra_y", "hra_z", "nps_employer_percent", "current_da_percent")

    def get_current_da_percent(self, obj) -> str:
        from django.utils import timezone

        from apps.payroll.services import da_percent_on

        return str(da_percent_on(obj, timezone.localdate()))


class PayCellSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayCell
        fields = ("index", "basic")


class PayLevelSerializer(BranchScopedSerializer):
    cells = PayCellSerializer(many=True)
    rule_set_name = serializers.CharField(source="rule_set.name", read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = PayLevel
        fields = ("id", "branch", "rule_set", "rule_set_name", "code", "sequence", "cells", "summary")

    def get_summary(self, obj) -> str:
        cells = sorted(obj.cells.all(), key=lambda c: c.index)
        if not cells:
            return ""
        return f"₹{cells[0].basic:,.0f} – ₹{cells[-1].basic:,.0f} ({len(cells)} cells)"

    def validate_cells(self, cells):
        idx = [c["index"] for c in cells]
        if len(idx) != len(set(idx)):
            raise serializers.ValidationError("Each cell number once.")
        ordered = sorted(cells, key=lambda c: c["index"])
        if any(b["basic"] <= a["basic"] for a, b in zip(ordered, ordered[1:])):
            raise serializers.ValidationError("Basic pay must rise from one cell to the next.")
        return cells

    def _save_cells(self, level, cells):
        if cells is None:
            return
        keep = {c["index"] for c in cells}
        if level.structures.exclude(cell_index__in=keep).exists():
            raise serializers.ValidationError({"cells": "A cell some staff are on cannot be removed."})
        level.cells.exclude(index__in=keep).delete()
        for c in cells:
            PayCell.objects.update_or_create(level=level, index=c["index"], defaults={"basic": c["basic"], "branch": level.branch})

    def create(self, validated_data):
        cells = validated_data.pop("cells")
        level = super().create(validated_data)
        self._save_cells(level, cells)
        return level

    def update(self, instance, validated_data):
        cells = validated_data.pop("cells", None)
        level = super().update(instance, validated_data)
        self._save_cells(level, cells)
        return level


class DARateSerializer(BranchScopedSerializer):
    rule_set_name = serializers.CharField(source="rule_set.name", read_only=True)

    class Meta:
        model = DARate
        fields = ("id", "branch", "rule_set", "rule_set_name", "effective_from", "percent", "declared_on", "note")
        read_only_fields = fields


class ReviseDASerializer(serializers.Serializer):
    percent = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0"))
    effective_from = serializers.DateField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PayComponentSerializer(BranchScopedSerializer):
    class Meta:
        model = PayComponent
        fields = ("id", "branch", "rule_set", "code", "name", "name_hi", "kind", "calc", "value", "taxable", "prorate",
                  "applies_to_all", "sequence")


def _slabs(value, key):
    if not isinstance(value, list):
        raise serializers.ValidationError("A list of slabs.")
    prev_to = None
    for i, s in enumerate(value):
        if not isinstance(s, dict) or "from" not in s or key not in s:
            raise serializers.ValidationError(f"Slab {i + 1}: needs from, to and {key}.")
        try:
            lo = Decimal(str(s["from"]))
            hi = None if s.get("to") in (None, "") else Decimal(str(s["to"]))
            Decimal(str(s[key]))
        except Exception as exc:
            raise serializers.ValidationError(f"Slab {i + 1}: numbers only.") from exc
        if hi is not None and hi < lo:
            raise serializers.ValidationError(f"Slab {i + 1}: 'to' is below 'from'.")
        if prev_to is not None and lo <= prev_to:
            raise serializers.ValidationError(f"Slab {i + 1} overlaps the one before.")
        if hi is None and i != len(value) - 1:
            raise serializers.ValidationError("Only the last slab can be open-ended.")
        prev_to = hi
    return value


class StatutorySettingsSerializer(BranchScopedSerializer):
    class Meta:
        model = StatutorySettings
        fields = ("id", "branch", "pf_employee_percent", "pf_employer_percent", "eps_percent", "pf_wage_ceiling",
                  "pf_cap_wages", "nps_employee_percent", "esi_employee_percent", "esi_employer_percent",
                  "esi_wage_ceiling", "pt_slabs", "tds_slabs", "tds_standard_deduction", "tds_rebate_limit",
                  "tds_cess_percent", "updated_at")
        read_only_fields = ("updated_at",)

    def validate_pt_slabs(self, v):
        return _slabs(v, "amount")

    def validate_tds_slabs(self, v):
        return _slabs(v, "percent")


class StructureComponentSerializer(serializers.ModelSerializer):
    serializer_related_field = ScopedPrimaryKeyRelatedField
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = StructureComponent
        fields = ("component", "component_name", "amount")


class SalaryStructureSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    rule_set_name = serializers.CharField(source="rule_set.name", read_only=True)
    level_code = serializers.CharField(source="level.code", read_only=True, default=None)
    basic = serializers.SerializerMethodField()
    overrides = StructureComponentSerializer(many=True, required=False)

    class Meta:
        model = SalaryStructure
        fields = ("id", "branch", "staff", "staff_name", "employee_code", "rule_set", "rule_set_name", "level", "level_code",
                  "cell_index", "fixed_basic", "basic", "city_class", "increment_month", "last_increment_on", "da_applicable",
                  "hra_applicable", "pf", "nps", "esi", "pt", "tds", "fixed_monthly_tds", "is_active", "overrides")
        read_only_fields = ("last_increment_on",)

    def get_basic(self, obj) -> str | None:
        from apps.payroll.services import basic_of

        try:
            return str(basic_of(obj))
        except Exception:
            return None

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        if get("pf") and get("nps"):
            raise serializers.ValidationError({"nps": "A staff member is on PF or on NPS, not both."})
        level, cell, fixed = get("level"), get("cell_index"), get("fixed_basic")
        if fixed is None and (level is None or cell is None):
            raise serializers.ValidationError({"level": "Choose a pay level and cell, or enter a fixed basic."})
        if level is not None and level.rule_set_id != get("rule_set").pk:
            raise serializers.ValidationError({"level": "That level belongs to another rule set."})
        if level is not None and cell is not None and not level.cells.filter(index=cell).exists():
            raise serializers.ValidationError({"cell_index": f"Level {level.code} has no cell {cell}."})
        if "increment_month" in attrs and attrs["increment_month"] not in range(0, 13):
            raise serializers.ValidationError({"increment_month": "0 (none) or 1–12."})
        for o in attrs.get("overrides") or []:
            if o["component"].rule_set_id != get("rule_set").pk:
                raise serializers.ValidationError({"overrides": f"{o['component'].name} belongs to another rule set."})
        staff = attrs.get("staff")
        if self.instance is None and staff and SalaryStructure.objects.filter(staff=staff).exists():
            raise serializers.ValidationError({"staff": "This staff member already has a salary structure; edit it."})
        return attrs

    def _save_overrides(self, structure, overrides):
        if overrides is None:
            return
        structure.overrides.all().delete()
        for o in overrides:
            StructureComponent.objects.create(branch=structure.branch, structure=structure, component=o["component"],
                                              amount=o["amount"])

    def create(self, validated_data):
        overrides = validated_data.pop("overrides", [])
        s = super().create(validated_data)
        self._save_overrides(s, overrides)
        return s

    def update(self, instance, validated_data):
        overrides = validated_data.pop("overrides", None)
        s = super().update(instance, validated_data)
        self._save_overrides(s, overrides)
        return s


class LoanSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = Loan
        fields = ("id", "branch", "staff", "staff_name", "kind", "amount", "monthly_recovery", "start_month", "balance",
                  "status", "note", "created_at")
        read_only_fields = ("balance", "status", "created_at")

    def validate(self, attrs):
        if self.instance is not None:
            for f in ("staff", "amount", "start_month", "kind"):
                if f in attrs and attrs[f] != getattr(self.instance, f):
                    raise serializers.ValidationError({f: "Can't be changed once recovery has started; close and re-enter."})
        return attrs


class OneTimePaymentSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = OneTimePayment
        fields = ("id", "branch", "staff", "staff_name", "month", "kind", "amount", "taxable", "note")

    def validate_month(self, v):
        return v.replace(day=1)

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("More than zero.")
        return v


class PayslipLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayslipLine
        fields = ("code", "name", "kind", "amount", "taxable")


class PayslipSerializer(BranchScopedSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    employee_code = serializers.CharField(source="staff.employee_code", read_only=True)
    run_status = serializers.CharField(source="run.status", read_only=True)
    lines = PayslipLineSerializer(many=True, read_only=True)

    class Meta:
        model = Payslip
        fields = ("id", "branch", "run", "run_status", "staff", "staff_name", "employee_code", "month", "rule_set_code",
                  "level", "cell_index", "basic_full", "da_percent", "days_in_month", "lop_days", "paid_days", "gross",
                  "total_deductions", "net_pay", "tds", "employer_epf", "employer_eps", "employer_nps", "employer_esi", "lines")
        read_only_fields = fields


class PayrollRunSerializer(BranchScopedSerializer):
    totals = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = ("id", "branch", "month", "status", "created_by", "locked_by", "locked_at", "reversed_by", "reversed_at",
                  "reversal_reason", "notes", "totals", "created_at")
        read_only_fields = ("status", "created_by", "locked_by", "locked_at", "reversed_by", "reversed_at",
                            "reversal_reason", "notes", "totals", "created_at")

    def get_totals(self, obj) -> dict:
        from apps.payroll.services import summary

        return {k: str(v) for k, v in summary(obj).items()}

    def validate_month(self, v):
        return v.replace(day=1)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField()
